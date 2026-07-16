# Momentum Routine

Lean, headless replacement for the dashboard app: one scheduled EOD job, one
digest email with 0–3 complete trade plans, backtest-validated thresholds,
live outcome tracking. Full context and measured results: `../PLAN.md`.

## Daily flow (automatic once scheduled)

fetch (yfinance EOD) → indicators → score+PBSS → regime gate → screen →
exit checks on open trades → outcome labeling → **one HTML email**.

Alert rule (measured, 2025-06→2026-06): **PBSS ≥ 18 AND score ≥ 79** →
+4.1% avg 21-day return, 55% win rate vs +0.2% / 45% baseline. High-conviction
tag at PBSS ≥ 20. No new buys in RISK_OFF regime (Nifty < 200DMA falling,
or VIX ≥ 22 downgrade).

## Setup (once, ~15 min)

```
# 0. revoke the OLD committed Gmail app password; create a new one
copy .env.example .env       # then edit .env
.venv\Scripts\activate
pip install yfinance
python -m routine.utils.bootstrap_from_lake   # seed OHLCV store from lake history
python -m routine.fetch                        # yfinance top-up + ^NSEI + ^INDIAVIX
python -m routine.run_daily --dry-run          # inspect routine_data/out/digest_*.html
python -m routine.run_daily                    # sends the real email
powershell -ExecutionPolicy Bypass -File routine\setup_task.ps1   # 18:45 Mon-Fri
```

## Commands

```
python -m routine.run_daily [--dry-run] [--no-fetch] [--limit N]
python -m routine.fetch [--symbols RELIANCE TCS] [--limit N]
python -m routine.state open RELIANCE 2891.5 10 --stop 2750 --t1 3180 --t2 3470
python -m routine.state close RELIANCE 3050
python -m routine.state list
python -m routine.run_backtest [--thresholds 16 18 20] [--start 2025-06-01]
python -m routine.utils.inspect_parquet
python -m routine.utils.validate_data
python -m pytest routine/tests -q               # 39 tests
```

## Config

Tunables: `routine_config.py` (thresholds, capital, risk %, ATR stop, targets,
timeout). Secrets: `.env` only (SMTP_*, DIGEST_TO, ROUTINE_CAPITAL,
ROUTINE_RISK_PCT). Universe: newest lake snapshot, or override with
`routine_data/universe.txt` (one symbol per line).

## Trade workflow

The digest proposes; you decide. If you take a trade, record it:
`python -m routine.state open <SYM> <price> <qty> --stop S --t1 A --t2 B`.
From then on the digest watches it and tells you when to exit
(STOP / T1 partial / T2 / 20-day timeout). Every alert is auto-labeled with
its real 21-day outcome and the rolling hit rate appears in each digest —
the system grades itself.
