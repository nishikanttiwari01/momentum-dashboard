# Momentum Routine — Rebuild Plan & Status

Context for any future session (Cowork or Claude Code in VS Code): read this
before touching code. Updated 2026-07-05 after Phase 1 + Phase 2 build.

## Decision

The dashboard app (FastAPI + React + orchestrator) is being retired in favor of
a **headless daily routine** in `routine/`. Keep the brain (indicators, scoring,
parquet data), scrap the machinery. Verified problems in the old app: hardcoded
fake statistics in alert emails, two parallel alert systems (orchestrator
force-fires every rule), 1,875-line god service, silent `except: pass`
failures, alerts only fire when the app is manually launched, and a committed
Gmail app password in configs/alerts.yaml (**must be revoked**).

## Architecture (agreed + built)

- Deterministic Python does all trading math. No n8n. No LLM in the signal path.
- One digest email per trading day at 18:45 IST via Windows Task Scheduler.
- Loud failures: crash -> error email + non-zero exit.
- EOD only; intraday dropped. Regime gate instead of more signals.
- News (future, defensive only): earnings-proximity veto, ASM/GSM check,
  red-flag headlines on shortlisted names. Never news sentiment scores.

## Backtest findings — CORRECTED (supersedes the first run)

First run mistakenly used the `close` column, which is empty before 2026-05
(old snapshots populate only `last`). Corrected engine coalesces close/last.
Effective sample: **2025-06-02 -> 2026-06-02, 223 signal days, 262,094 liquid
symbol-day rows** (liquidity data only exists from ~2025-06).

| Rule (cooldown 5TD, liq >= Rs 1cr/day) | n | fwd21 mean | median | win% | >=10% hit |
|---|---|---|---|---|---|
| baseline (all liquid) | 262,094 | +0.2% | -1.2% | 45.1 | 17.5% |
| PBSS>=16 (old app's WATCHLIST alert) | 2,887 | -0.3% | -2.4% | 41.6 | 18.3% |
| PBSS>=18 | 1,078 | +1.1% | -1.1% | 46.6 | 23.2% |
| PBSS>=20 | 255 | +2.1% | +0.3% | 50.2 | 26.3% |
| **PBSS>=18 & score>=79 (chosen rule)** | **313** | **+4.1%** | **+1.6%** | **55.3** | **26.8%** |
| PBSS>=18 & regime!=DOWN | 681 | +3.0% | +0.5% | 51.5 | 26.4% |

Conclusions:
1. PBSS alone below 20 is noise-to-negative. The old app's PBSS>=16 email was
   measurably WORSE than baseline (median -2.4%).
2. The edge lives in the COMBINATION: PBSS>=18 AND composite score>=79 (ELITE).
   This is the production alert rule in `routine_config.py`.
3. Regime matters hugely: same signals in a DOWN market average -2.6%. The
   Nifty-200DMA regime gate (regime.py) blocks new buys in RISK_OFF and halves
   size in CAUTION. India VIX >= 22 downgrades one level.
4. All figures gross; subtract ~0.3-0.5%/round trip. ~10% of even good signals
   land in the worst decile at -14%; the ATR stop caps that.
5. Old app's claims ("43.8% surge rate", "~12% hit rate") were fabricated
   constants; nothing close survives measurement.

## Status

### Phase 1 — backtest harness: DONE
`routine/`: backtest.py, pbss.py (vectorized == app logic, proven by tests),
data_io.py (handles `last` coalescing, partial/empty rerun partitions),
report.py, run_backtest.py, utils/inspect_parquet.py, utils/validate_data.py.

### Phase 2 — daily routine: DONE (needs first real run on Windows)
- fetch.py — incremental yfinance EOD store (routine_data/ohlcv/), injectable
  downloader, per-symbol failure isolation. Universe from newest lake snapshot
  (strips the `.NS` suffix the lake uses).
- utils/bootstrap_from_lake.py — one-time seeding of the OHLCV store from
  484 days of lake history (2,049 symbols seeded in the smoke run). Pre-2026-05
  bars approximate OHLC with close; yfinance overwrites going forward.
- regime.py — Nifty 200DMA + slope + VIX -> RISK_ON / CAUTION / RISK_OFF.
- screen.py — indicators -> compute_score -> PBSS -> combined-rule gate ->
  liquidity floor -> cooldown -> top-3 by PBSS.
- sizing.py — ATR(2x) stop, T1 +10% / T2 +20%, 1% capital risk, position
  capped at capital, NSE tick rounding. (ROUTINE_CAPITAL env, default 5L.)
- state.py — SQLite alerts/trades; exits STOP/T1/T2/TIMEOUT(20TD); outcome
  labeling at +5/+21TD; rolling live hit-rate. CLI: open/close/list.
- digest.py + notify.py + run_daily.py — HTML digest (stale-data warning,
  regime header, full trade plans, live outcomes, measured-stats table),
  env-only SMTP, error email on crash.
- setup_task.ps1 — Task Scheduler registration (18:45 Mon-Fri, WakeToRun).
- 39 tests green. Smoke run on real data: 400 symbols in ~25s, 1 idea
  (BLSE PBSS 19 score 88, full plan rendered).

### To go live (user, ~15 min, in order)
1. Revoke the old Gmail app password; create a new one.
2. `copy .env.example .env` and fill it in.
3. `pip install yfinance` in the venv (only new dependency).
4. `python -m routine.utils.bootstrap_from_lake`  (one-time, ~2 min)
5. `python -m routine.fetch`                      (first yfinance top-up + ^NSEI/^INDIAVIX)
6. `python -m routine.run_daily --dry-run`        (inspect routine_data/out/*.html)
7. `python -m routine.run_daily`                  (real email)
8. `powershell -ExecutionPolicy Bypass -File routine\setup_task.ps1`

### Phase 2.5 — watchlist + movers (2026-07-11): DONE
LIVE since 2026-07-05 (task registered, first real runs OK). User pushback
after a week of blank RISK-OFF digests. Mover-pattern study on the routine
OHLCV store (91,083 liquid symbol-days, Aug 2024 -> Jul 2026, >=1cr, >Rs 20):
- Chasing the day's top-10 gainers: fwd21 +0.2% vs +2.3% baseline (NEGATIVE
  relative edge); next-day median -0.1%, win 47%.
- +5% gainers: next-day mean +0.5% but median 0.0 — skew, not tradeable after
  costs. -10% crashes CONTINUE falling (-1.2% next day, -2.1% at 5d).
- A top-10 gainer repeats in tomorrow's top-10 19.5% of the time (vs ~3%
  random) — clustering exists but not monetizable (can't know which one).
- Regime-split numbers unreliable (liquidity data concentrated in the recent
  RISK_OFF stretch); only overall numbers quoted in MOVERS_NOTE.
Digest changes (43 tests green):
- Watchlist section: top-5 near-misses (PBSS>=15 or score>=70) AND
  regime-blocked elite ideas, labeled NOT buys, no trade plans on purpose.
- Movers section: top-5 liquid gainers/losers + MOVERS_NOTE quoting the
  measured no-edge stats so it is never mistaken for signals.
- New files: routine/movers.py, routine/tests/test_watchlist_movers.py.
  Subject shows "N watching" on idea-less days.
- Advisory Claude scheduled task "digest-news-veto-check" (21:30 Mon-Fri,
  Cowork): earnings-proximity / ASM-GSM / red-flag news veto on digest ideas.
  Runs on next app launch if missed; advisory only, never in the signal path.

### Phase 2.6 — index dip signal (2026-07-11): DONE
User trades NIFTYBEES dips profitably by feel; measured it on 19y of ^NSEI /
^NSEBANK (routine/utils/index_dip_study.py, CSV in routine/reports/):
- RSI(2)<10 & ABOVE 200DMA, exit first up-close (max 10 TD): Nifty
  +0.35%/trade gross, win 89%, worst 5d -5.6%, ~17/yr. BankNifty +0.25%,
  win 86%, worst -8.2%.
- Same trade BELOW the 200DMA: ~0 to negative per trade, worst 5d -19% to
  -22%. The 200DMA gate IS the strategy. (User's recent below-200DMA wins
  were variance, not edge — told him so.)
- Deep dips (5d ret < -2/-3%) also negative: buy shallow pullbacks, not knives.
Implementation (49 tests green): routine/index_dip.py — deterministic,
DB-free position reconstruction from the close series (entry = last signal
close, exit = first up-close/timeout); ^NSEBANK added to daily fetch; digest
section "Index dip" with BUY/HOLD/EXIT/OFF-SEASON status + INDEX_DIP_STATS
caption; subject line flags dip BUY/SELL days. Live check: NIFTY = OFF_SEASON
(RSI2 69, -2.6% below 200DMA).

### Phase 3 — next
Two weeks of parallel running, then: retire the old app; weekly Claude review
of the outcomes DB; revisit thresholds only via
`python -m routine.run_backtest` evidence.

## Environment quirks (Cowork sandbox)
- The sandbox mount can serve stale/truncated reads of recently edited files
  and cannot delete `__pycache__`; run tests from a copy in /tmp. Native
  Windows has no such issue.
- Lake facts: symbols stored as "X.NS"; `close`/OHLCV columns empty before
  ~2026-05 (`last` is the price); ret_5d & median_traded_value exist from
  ~2025-06; some partitions contain partial/empty rerun files (data_io picks
  the max-row file); 2025-10-17 partition is empty.
