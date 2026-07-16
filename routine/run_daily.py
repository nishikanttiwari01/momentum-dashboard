"""Daily orchestrator: fetch -> screen -> exits -> outcomes -> digest email.

Fails LOUDLY: any unhandled error sends an error email and exits non-zero.

Usage:
    python -m routine.run_daily                # full run, sends email
    python -m routine.run_daily --dry-run      # no email; writes HTML to out/
    python -m routine.run_daily --no-fetch     # skip data update (reuse store)
    python -m routine.run_daily --limit 50     # small universe (smoke test)
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import date, datetime

from . import digest, fetch, index_dip, movers as movers_mod, notify, regime as regime_mod, routine_config, screen, state, universe

log = logging.getLogger("routine.daily")


def _price_lookup_factory():
    cache = {}

    def lookup(symbol: str, day_iso: str):
        df = cache.get(symbol)
        if df is None:
            df = fetch.load_ohlcv(symbol)
            df = df.set_index(df["date"].astype(str)) if len(df) else df
            cache[symbol] = df
        if df is None or len(df) == 0 or day_iso not in df.index:
            return None
        try:
            return float(df.loc[day_iso, "close"])
        except (KeyError, TypeError, ValueError):
            return None

    return lookup


def run(dry_run: bool = False, no_fetch: bool = False, limit: int = 0) -> int:
    routine_config.load_dotenv()
    routine_config.ensure_dirs()
    today = date.today()
    cfg = routine_config.DAILY

    logfile = routine_config.OUT_DIR / f"run_{today.isoformat()}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(logfile, encoding="utf-8"), logging.StreamHandler()],
    )

    uni = universe.load_universe()
    if limit:
        uni = uni.head(limit)
    symbols = uni["symbol"].tolist() + [routine_config.NIFTY_SYMBOL, routine_config.BANKNIFTY_SYMBOL, routine_config.VIX_SYMBOL]

    fetch_failures = 0
    if not no_fetch:
        log.info("updating %d symbols ...", len(symbols))
        res = fetch.update_symbols(symbols)
        fetch_failures = sum(1 for v in res.values() if v < 0)
        log.info("fetch done: %d new bars, %d failures",
                 sum(v for v in res.values() if v > 0), fetch_failures)

    # trading calendar = dates present for Nifty (fallback: any liquid symbol)
    nifty = fetch.load_ohlcv(routine_config.NIFTY_SYMBOL)
    calendar = [d.isoformat() for d in nifty["date"].tolist()] if len(nifty) else []
    data_date = fetch.freshness(uni["symbol"].tolist())

    reg = regime_mod.current_regime()
    log.info("regime: %s (%s)", reg.label, reg.description)

    conn = state.connect()
    lookup = _price_lookup_factory()

    recent = state.recent_alert_symbols(conn, calendar, cfg.cooldown_days)
    open_syms = {t["symbol"] for t in state.open_trades(conn)}
    screen_res = screen.run_screen(uni, reg, recent_alert_symbols=recent | open_syms)
    log.info("screen: %d scanned, %d above threshold, %d ideas, %d watching",
             screen_res.scanned, screen_res.candidates_above_watch,
             len(screen_res.ideas), len(screen_res.watchlist))

    mov = movers_mod.compute_movers(uni)
    log.info("movers: %d gainers / %d losers", len(mov["gainers"]), len(mov["losers"]))

    dips = index_dip.compute_dip_statuses()
    for d in dips:
        log.info("index dip %s: %s (%s)", d.index_name, d.label, d.note)

    exit_events = []
    if calendar:
        today_bar = calendar[-1]
        exit_events = state.check_exits(conn, lookup, today_bar, calendar, cfg.timeout_days)
    labeled = state.label_outcomes(conn, lookup, calendar)
    log.info("labeled %d alert outcomes", labeled)

    state.record_alerts(conn, today.isoformat(), screen_res.ideas)
    outcome = state.outcome_stats(conn)
    positions = [dict(t) for t in state.open_trades(conn)]

    html = digest.render_html(
        today=today, regime=reg, screen_res=screen_res, exit_events=exit_events,
        open_positions=positions, outcome=outcome, data_date=data_date,
        fetch_failures=fetch_failures, movers=mov, dips=dips,
    )
    subject = digest.render_subject(today, screen_res, exit_events, reg, dips=dips)

    out_html = routine_config.OUT_DIR / f"digest_{today.isoformat()}.html"
    out_html.write_text(html, encoding="utf-8")
    log.info("digest written: %s", out_html)

    if dry_run:
        print(f"[dry-run] subject: {subject}")
        print(f"[dry-run] html: {out_html}")
    else:
        notify.send_email(subject, html)
        print(f"sent: {subject}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="momentum daily routine")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args(argv)
    try:
        return run(dry_run=args.dry_run, no_fetch=args.no_fetch, limit=args.limit)
    except Exception as exc:  # loud failure: notify + non-zero exit
        traceback.print_exc()
        if not args.dry_run:
            notify.send_error("daily routine crashed", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
