# backend/app/notifs/email_digest.py
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Iterable, Optional, List, Tuple
from datetime import date, datetime
from app.core.config import load as cfg_load
from app.repos.parquet.scores_repo import ScoresRepo

# Trades are optional (if SQL is wired)
try:
    from app.core.db import get_sessionmaker
    from app.repos.sql.positions_repo import PositionsRepo
    HAVE_DB = True
except Exception:
    HAVE_DB = False

log = logging.getLogger("app.notifs.email_digest")


# ----------------------------
# Helpers: config + formatting
# ----------------------------

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
        "include_trades": bool(e.get("include_trades", True)),
        "smtp_host": e.get("smtp_host"),
        "smtp_port": int(e.get("smtp_port") or 587),
        "use_tls": bool(e.get("use_tls", True)),
        "username": e.get("username"),
        "password": e.get("password"),
        "from_addr": e.get("from_addr") or e.get("username"),
        "from_name": e.get("from_name") or "Momentum Suite",
        "to_list": _coerce_emails(e.get("to_list")),
    }

def _pct(v: Any) -> str:
    try:
        f = float(v)
        return f"{'+' if f > 0 else ''}{f:.2f}%"
    except Exception:
        return ""

def _price(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return ""


# ----------------------------
# HTML builders
# ----------------------------

def _build_table_html(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    """Safe (escaped) table builder with nicer default styles."""
    def esc(x: Any) -> str:
        s = "" if x is None else str(x)
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ths = "".join(
        f"<th style='text-align:left;padding:8px 10px;background:#f7f9fc;"
        f"border-bottom:1px solid #e6e9ef;font-weight:600'>{esc(h)}</th>"
        for h in headers
    )
    trs = []
    for r in rows:
        tds = "".join(
            f"<td style='padding:8px 10px;border-bottom:1px solid #f1f3f7'>{esc(c)}</td>"
            for c in r
        )
        trs.append(f"<tr>{tds}</tr>")
    body = "".join(trs)
    return (
        "<table style='border-collapse:collapse;width:100%;margin:8px 0;"
        "border:1px solid #e6e9ef;border-radius:8px;overflow:hidden'>"
        f"<thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table>"
    )

def _build_table_html_raw(headers: Iterable[str], rows_html: Iterable[Iterable[str]]) -> str:
    """
    Same as above but DOES NOT escape <td> contents (so we can inject colored spans).
    Only use with trusted data we generate ourselves.
    """
    def esc(x: Any) -> str:
        s = "" if x is None else str(x)
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ths = "".join(
        f"<th style='text-align:left;padding:8px 10px;background:#f7f9fc;"
        f"border-bottom:1px solid #e6e9ef;font-weight:600'>{esc(h)}</th>"
        for h in headers
    )
    trs = []
    for r in rows_html:
        tds = "".join(
            f"<td style='padding:8px 10px;border-bottom:1px solid #f1f3f7'>{cell}</td>"
            for cell in r
        )
        trs.append(f"<tr>{tds}</tr>")
    body = "".join(trs)
    return (
        "<table style='border-collapse:collapse;width:100%;margin:8px 0;"
        "border:1px solid #e6e9ef;border-radius:8px;overflow:hidden'>"
        f"<thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table>"
    )


# ----------------------------
# Data pulls
# ----------------------------

def _top_lists_for_day(as_of_day: date, scores: ScoresRepo) -> Tuple[list[dict], list[dict], list[dict], Optional[str]]:
    cols = ["symbol", "name", "sector", "last", "change_pct", "pct_1d", "score"]
    # 1D movers (prefer change_pct; fall back to pct_1d)
    gainers, _, rid_up, _ = scores.read(
        run_id=None, as_of_str=as_of_day.isoformat(),
        filters={}, sort="change_pct.desc,pct_1d.desc,score.desc",
        page=1, per_page=5, columns=cols,
    )
    losers, _, rid_dn, _ = scores.read(
        run_id=None, as_of_str=as_of_day.isoformat(),
        filters={}, sort="change_pct.asc,pct_1d.asc,score.desc",
        page=1, per_page=5, columns=cols,
    )
    scorers, _, rid_sc, _ = scores.read(
        run_id=None, as_of_str=as_of_day.isoformat(),
        filters={}, sort="score.desc,last.desc",
        page=1, per_page=5, columns=cols,
    )
    rid = rid_up or rid_dn or rid_sc
    return (gainers or []), (losers or []), (scorers or []), rid

def _active_trades_html() -> str:
    """Build the Active Trades table — only Symbol / Qty / Entry as requested."""
    if not HAVE_DB:
        return ""
    try:
        # Make this fail-safe when DB isn't initialized (e.g., CLI dry-run)
        try:
            sm = get_sessionmaker()
        except RuntimeError:
            # DB not initialized in this process → skip quietly
            log.info("active_trades_skipped_db_not_initialized")
            return ""
        except Exception:
            log.exception("active_trades_sessionmaker_failed")
            return ""        
        with sm() as s:
            repo = PositionsRepo(s)
            pos = repo.list_positions() or []
        active = [p for p in pos if p.get("trade_on")]
        if not active:
            return ""
        rows = []
        for p in active:
            rows.append((
                p.get("symbol", ""),
                p.get("qty") or "",
                _price(p.get("entry_price_locked")),
            ))
        table = _build_table_html(["Symbol", "Qty", "Entry"], rows)
        return f"<h3>Active Trades</h3>{table}"
    except Exception:
        # Keep email clean even if trades section fails
        log.info("active_trades_section_failed", exc_info=True)
        return ""


# ----------------------------
# Render email
# ----------------------------

def _render_html(
    as_of_day: date,
    gainers: list[dict],
    losers: list[dict],
    scorers: list[dict],
    run_id: Optional[str],
    include_trades_html: str
) -> Tuple[str, str, str]:

    subj = f"Momentum Suite — Summary for {as_of_day.isoformat()}"

    GREEN = "#0B8A3C"
    RED = "#C62828"

    # Gainers/Losers rows: no Name column; color Δ 1D
    def rows_gainers(lst: list[dict]) -> list[list[str]]:
        out: list[list[str]] = []
        for r in lst or []:
            pct_val = r.get("change_pct")
            pct_s = _pct(pct_val if pct_val is not None else r.get("pct_1d"))
            out.append([
                (r.get("symbol") or ""),
                _price(r.get("last")),
                f"<span style='color:{GREEN};font-weight:600'>{pct_s}</span>",
                (f"{float(r.get('score')):.1f}" if r.get("score") is not None else ""),
            ])
        return out

    def rows_losers(lst: list[dict]) -> list[list[str]]:
        out: list[list[str]] = []
        for r in lst or []:
            pct_val = r.get("change_pct")
            pct_s = _pct(pct_val if pct_val is not None else r.get("pct_1d"))
            out.append([
                (r.get("symbol") or ""),
                _price(r.get("last")),
                f"<span style='color:{RED};font-weight:600'>{pct_s}</span>",
                (f"{float(r.get('score')):.1f}" if r.get("score") is not None else ""),
            ])
        return out

    def rows_plain(lst: list[dict]) -> list[tuple[str, str, str, str]]:
        """Plain (no color) rows for text and Top Scorers HTML (also no Name)."""
        out: list[tuple[str, str, str, str]] = []
        for r in lst or []:
            pct_val = r.get("change_pct")
            pct_s = _pct(pct_val if pct_val is not None else r.get("pct_1d"))
            out.append((
                (r.get("symbol") or ""),
                _price(r.get("last")),
                pct_s,
                (f"{float(r.get('score')):.1f}" if r.get("score") is not None else ""),
            ))
        return out

    h_gain = _build_table_html_raw(["Symbol", "Price", "Δ 1D", "Score"], rows_gainers(gainers))
    h_lose = _build_table_html_raw(["Symbol", "Price", "Δ 1D", "Score"], rows_losers(losers))
    h_score = _build_table_html(["Symbol", "Price", "Δ 1D", "Score"], rows_plain(scorers))

    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;font-size:14px;line-height:1.5;color:#222">
      <h2 style="margin:0 0 8px">Momentum Suite — Summary <b>{as_of_day.isoformat()}</b></h2>
      <h3>Top 5 Gainers (1D)</h3>{h_gain}
      <h3>Top 5 Losers (1D)</h3>{h_lose}
      <h3>Top 5 by Score</h3>{h_score}
      {include_trades_html}
      <p style="color:#666;margin-top:16px">Run ID: {run_id or ''}</p>
    </div>
    """

    # Plain-text fallback
    def txt_block(title: str, rows: list[tuple[str, str, str, str]]) -> str:
        lines = [title]
        for r in rows:
            lines.append("  " + " | ".join(r))
        return "\n".join(lines)

    t_gain = rows_plain(gainers)
    t_lose = rows_plain(losers)
    t_score = rows_plain(scorers)

    text = f"Momentum Suite — Summary for {as_of_day.isoformat()}\n\n"
    text += txt_block("Top 5 Gainers (1D)", t_gain) + "\n\n"
    text += txt_block("Top 5 Losers (1D)", t_lose) + "\n\n"
    text += txt_block("Top 5 by Score", t_score) + "\n"

    return subj, html, text


# ----------------------------
# Send email
# ----------------------------

def _send_email(cfg: dict, subject: str, html_body: str, text_body: Optional[str]) -> None:
    host = cfg.get("smtp_host")
    port = int(cfg.get("smtp_port") or 587)
    username = cfg.get("username")
    password = cfg.get("password")
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


# ----------------------------
# Public entry points
# ----------------------------

def send_backfill_digest_if_enabled(as_of_day: date) -> bool:
    """
    Call this after a successful day’s backfill.
    Returns True if attempted (and likely sent), False if disabled/misconfigured.
    """
    cfg = _email_cfg()
    if not (cfg.get("enabled") and cfg.get("on_backfill_digest")):
        log.info("email_digest_disabled", extra={"enabled": cfg.get("enabled"), "on_backfill_digest": cfg.get("on_backfill_digest")})
        return False

    scores = ScoresRepo()
    gainers, losers, scorers, run_id = _top_lists_for_day(as_of_day, scores)
    trades_html = _active_trades_html() if cfg.get("include_trades", True) else ""
    subject, html, text = _render_html(as_of_day, gainers, losers, scorers, run_id, trades_html)

    try:
        _send_email(cfg, subject, html, text)
        log.info("email_digest_sent", extra={"as_of": as_of_day.isoformat(), "to": cfg.get("to_list"), "run_id": run_id})
        return True
    except Exception:
        log.exception("email_digest_send_failed", extra={"as_of": as_of_day.isoformat()})
        return False


# ----------------------------
# CLI (python -m app.notifs.email_digest ...)
# ----------------------------

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(
        prog="email_digest",
        description="Send (or preview) the Momentum Suite backfill email digest for a given date."
    )
    parser.add_argument("-d", "--date", help="Backfill date in YYYY-MM-DD. Defaults to today (local).", default=None)
    parser.add_argument("--send", action="store_true", help="Actually send the email. If omitted, shows a dry-run preview.")
    parser.add_argument("--override-to", help="Comma-separated recipients to override config to_list.", default=None)
    parser.add_argument("--save-html", help="Optional path to save the rendered HTML preview (dry-run or send).", default=None)
    parser.add_argument("--save-text", help="Optional path to save the plain-text preview (dry-run or send).", default=None)
    args = parser.parse_args()

    as_of_day = (datetime.now().date() if not args.date else datetime.fromisoformat(args.date).date())

    cfg = _email_cfg()
    scores = ScoresRepo()
    gainers, losers, scorers, run_id = _top_lists_for_day(as_of_day, scores)
    trades_html = _active_trades_html() if cfg.get("include_trades", True) else ""
    subject, html, text = _render_html(as_of_day, gainers, losers, scorers, run_id, trades_html)

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
