# backend/app/notifs/email_digest.py
from __future__ import annotations
import logging, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Iterable, Optional
from datetime import date

from app.core.config import load as cfg_load

# Data sources
from app.repos.parquet.scores_repo import ScoresRepo

# Trades are optional (if SQL is wired)
try:
    from app.core.db import get_sessionmaker
    from app.repos.sql.positions_repo import PositionsRepo
    HAVE_DB = True
except Exception:
    HAVE_DB = False

log = logging.getLogger("app.notifs.email_digest")

def _coerce_emails(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return []

def _email_cfg() -> dict:
    """Read alerts.email from config; provide sane defaults."""
    alerts = cfg_load().alerts or {}
    e = (alerts.get("email") or {})
    return {
        "enabled": bool(e.get("enabled", True)),
        "on_backfill_digest": bool(e.get("on_backfill_digest", True)),
        "smtp_host": e.get("smtp_host"),
        "smtp_port": int(e.get("smtp_port") or 587),
        "use_tls": bool(e.get("use_tls", True)),
        "username": e.get("username"),
        "password": e.get("password"),
        "from_addr": e.get("from_addr") or e.get("username"),
        "from_name": e.get("from_name") or "Momentum Suite",
        "to_list": _coerce_emails(e.get("to_list")),
    }

def _build_table_html(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    def esc(x: Any) -> str:
        s = "" if x is None else str(x)
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    ths = "".join(f"<th style='text-align:left;padding:6px 8px;border-bottom:1px solid #eee'>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td style='padding:6px 8px;border-bottom:1px solid #f5f5f5'>{esc(c)}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f"<table style='border-collapse:collapse;width:100%;margin:8px 0'><thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table>"

def _pct(v: Any) -> str:
    try:
        f = float(v)
        return f"{'+' if f>0 else ''}{f:.2f}%"
    except Exception:
        return ""

def _price(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return ""

def _top_lists_for_day(as_of_day: date, scores: ScoresRepo):
    cols = ["symbol","name","sector","last","change_pct","pct_1d","score"]
    # 1D movers (prefer change_pct; fall back to pct_1d)
    gainers, _, rid_up, _ = scores.read(
        run_id=None, as_of_str=as_of_day.isoformat(),
        filters={}, sort="change_pct.desc,pct_1d.desc,score.desc", page=1, per_page=5, columns=cols,
    )
    losers,  _, rid_dn, _ = scores.read(
        run_id=None, as_of_str=as_of_day.isoformat(),
        filters={}, sort="change_pct.asc,pct_1d.asc,score.desc", page=1, per_page=5, columns=cols,
    )
    scorers, _, rid_sc, _ = scores.read(
        run_id=None, as_of_str=as_of_day.isoformat(),
        filters={}, sort="score.desc,last.desc", page=1, per_page=5, columns=cols,
    )
    rid = rid_up or rid_dn or rid_sc
    return (gainers or []), (losers or []), (scorers or []), rid

def _render_html(as_of_day: date, gainers, losers, scorers, run_id: Optional[str], include_trades_html: str) -> tuple[str, str, str]:
    subj = f"Momentum Suite — Backfill Digest for {as_of_day.isoformat()}"

    def rows(lst):
        o = []
        for r in lst:
            pct = r.get("change_pct")
            o.append((
                r.get("symbol",""),
                r.get("name",""),
                _price(r.get("last")),
                _pct(pct if pct is not None else r.get("pct_1d")),
                f"{float(r.get('score')):.1f}" if r.get("score") is not None else "",
            ))
        return o

    h_gain = _build_table_html(["Symbol","Name","Price","Δ 1D","Score"], rows(gainers))
    h_lose = _build_table_html(["Symbol","Name","Price","Δ 1D","Score"], rows(losers))
    h_score = _build_table_html(["Symbol","Name","Price","Δ 1D","Score"], rows(scorers))

    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;font-size:14px;line-height:1.5;color:#222">
      <h2 style="margin:0 0 8px">Momentum Suite — Backfill Digest</h2>
      <p>Daily backfill digest for <b>{as_of_day.isoformat()}</b>.</p>
      <h3>Top 5 Gainers (1D)</h3>{h_gain}
      <h3>Top 5 Losers (1D)</h3>{h_lose}
      <h3>Top 5 by Score</h3>{h_score}
      {include_trades_html}
      <p style="color:#666;margin-top:16px">Run ID: {run_id or ''}</p>
    </div>
    """

    def txt(title, lst):
        return title + "\n" + "\n".join("  " + " | ".join(map(str, r)) for r in rows(lst)) + "\n"

    text = f"Momentum Suite — Backfill Digest {as_of_day.isoformat()}\n\n"
    text += txt("Top 5 Gainers (1D)", gainers) + "\n"
    text += txt("Top 5 Losers (1D)", losers) + "\n"
    text += txt("Top 5 by Score", scorers) + "\n"
    return subj, html, text

def _active_trades_html() -> str:
    if not HAVE_DB:
        return ""
    try:
        sm = get_sessionmaker()
        with sm() as s:
            repo = PositionsRepo(s)
            pos = repo.list_positions() or []
        active = [p for p in pos if p.get("trade_on")]
        if not active:
            return ""
        rows = []
        for p in active:
            rows.append((
                p.get("symbol",""),
                p.get("qty") or "",
                _price(p.get("entry_price_locked")),
                _price(p.get("stop_now")),
                "Yes" if p.get("breakeven_active") else "No",
                "Yes" if p.get("euphoria_on") else "No",
                p.get("note","") or "",
            ))
        table = _build_table_html(["Symbol","Qty","Entry","Stop","BE?","Euphoria?","Note"], rows)
        return f"<h3>Active Trades</h3>{table}"
    except Exception:
        log.exception("active_trades_section_failed")
        return ""

def _send_email(cfg: dict, subject: str, html_body: str, text_body: Optional[str]) -> None:
    host = cfg.get("smtp_host"); port = int(cfg.get("smtp_port") or 587)
    username = cfg.get("username"); password = cfg.get("password")
    from_addr = cfg.get("from_addr") or username
    from_name = cfg.get("from_name") or ""
    to_list = _coerce_emails(cfg.get("to_list"))
    use_tls = bool(cfg.get("use_tls", True))

    if not host or not to_list:
        log.warning("email_not_sent_missing_config", extra={"host": bool(host), "to": to_list})
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = ", ".join(to_list)
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    smtp = smtplib.SMTP(host, port)
    try:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.sendmail(from_addr, to_list, msg.as_string())
    finally:
        smtp.quit()

def send_backfill_digest_if_enabled(as_of_day: date) -> bool:
    cfg = _email_cfg()
    if not (cfg.get("enabled") and cfg.get("on_backfill_digest")):
        log.info("email_digest_disabled", extra={"enabled": cfg.get("enabled"), "on_backfill_digest": cfg.get("on_backfill_digest")})
        return False

    scores = ScoresRepo()
    gainers, losers, scorers, run_id = _top_lists_for_day(as_of_day, scores)
    trades_html = _active_trades_html()
    subject, html, text = _render_html(as_of_day, gainers, losers, scorers, run_id, trades_html)

    try:
        _send_email(cfg, subject, html, text)
        log.info("email_digest_sent", extra={"as_of": as_of_day.isoformat(), "to": cfg.get("to_list"), "run_id": run_id})
        return True
    except Exception:
        log.exception("email_digest_send_failed", extra={"as_of": as_of_day.isoformat()})
        return False

if __name__ == "__main__":
    import argparse, sys
    from datetime import datetime, timedelta
    from app.repos.parquet.scores_repo import ScoresRepo  # reuse existing repo

    parser = argparse.ArgumentParser(
        prog="email_digest",
        description="Send (or preview) the Momentum Suite backfill email digest for a given date."
    )
    parser.add_argument(
        "-d", "--date",
        help="Backfill date in YYYY-MM-DD. Defaults to today (local).",
        default=None,
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the email. If omitted, shows a dry-run preview."
    )
    parser.add_argument(
        "--override-to",
        help="Comma-separated recipients to override config to_list (e.g. you@x.com,me@y.com).",
        default=None,
    )
    parser.add_argument(
        "--save-html",
        help="Optional path to save the rendered HTML preview (dry-run or send).",
        default=None,
    )
    parser.add_argument(
        "--save-text",
        help="Optional path to save the plain-text preview (dry-run or send).",
        default=None,
    )

    args = parser.parse_args()
    as_of_day = (
        datetime.now().date() if not args.date
        else datetime.fromisoformat(args.date).date()
    )

    # Build content
    cfg = _email_cfg()
    scores = ScoresRepo()
    gainers, losers, scorers, run_id = _top_lists_for_day(as_of_day, scores)
    trades_html = _active_trades_html()
    subject, html, text = _render_html(as_of_day, gainers, losers, scorers, run_id, trades_html)

    # Optional overrides / saves
    if args.override_to:
        cfg["to_list"] = _coerce_emails(args.override_to)
    if args.save_html:
        with open(args.save_html, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[ok] HTML saved → {args.save_html}")
    if args.save_text:
        with open(args.save_text, "w", encoding="utf-8") as f:
            f.write(text or "")
        print(f"[ok] Text saved → {args.save_text}")

    if args.send:
        _send_email(cfg, subject, html, text)
        print(f"[sent] {subject} → {', '.join(cfg.get('to_list', []))}")
        sys.exit(0)
    else:
        # Dry-run preview
        print(f"[dry-run] Subject: {subject}")
        print(f"[dry-run] To: {', '.join(cfg.get('to_list', [])) or '(none)'}")
        print(f"[dry-run] First 200 chars of HTML:\n{(html or '')[:200]}…")
        sys.exit(0)
