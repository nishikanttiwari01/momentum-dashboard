# Scoring, Signals, and Next Actions

This doc summarises how scores and buy signals are produced, how `reason_parts` strings are built, and how the candidate pool is maintained (strict entry, relaxed exits).

## Data layout (parquet outputs)

```
backend/app/repos/parquet/
- datasets.py              # Defines datasets & partitions
- indicators_repo.py       # Reads indicators from OHLC parquet
- scores_repo.py           # Writes scores and related parquet outputs
- scores/
  - daily/                 # Daily (EOD) scores for swing-trade model
    - as_of=YYYY-MM-DD/part-0000.parquet, ...
  - intraday/              # Intraday scores for watchlists & live heatmaps
    - date=YYYY-MM-DD/part-0000.parquet, ...
```

Notes:
- The EOD model reads historical daily OHLC parquet files (used to compute RSI, ADX, ATR10, RelVol20, proximity to 52W high, base length, etc.).
- Intraday parquet files are refreshed by the scheduler every 15 minutes for watchlist updates.
- `base_len_bars` counts daily consolidation bars from historical daily data.

## Scoring overview

| Pillar | Components | Weight |
| --- | --- | --- |
| Momentum | RSI, ADX, DI+/DI-, ADX slope | 35% |
| Breakout Quality | 52W proximity, higher highs/lows, EMA cluster, ATR normalization | 30% |
| Accumulation & Volume | RelVol, OBV/CMF, volume expansion | 25% |
| Market/Sector Context | Index trend, sector breadth | 10% |

Final score = weighted sum of pillar scores (0-100).

## Buy evaluation and signals

### Pre-gates (soft filters, run before profile checks)

| Gate | Rule (default) | Purpose |
| --- | --- | --- |
| Close | >= 50 | Avoid illiquid/penny names |
| Score | >= 35 | Ensure base quality before deeper checks |
| RelVol20 | >= 0.9x | Filter out very quiet tape |
| ADX14 | >= 20 | Require at least an emerging trend |
| 52W proximity % | >= -12% | Avoid deep drawdowns |

### EOD breakout profile (`swing_eod`)
Strict: all nine checks must pass. Used for `buy_flag` and candidate pool entry.

| Gate | Rule (default) | Purpose |
| --- | --- | --- |
| Score | >= 70 | Overall quality floor |
| Pivot clear % | Between -0.3% and +6.0% | Must be near/through pivot without being overextended |
| Base length (bars) | >= 5 | Require at least a visible base |
| 52W proximity % | >= -8% | Stay near highs |
| RelVol20 | >= 1.3x | Volume confirmation |
| ADX14 | >= 22 | Trend strength |
| ATR% (10d) | Between 2% and 8% | Tradable volatility band |
| Day % change | <= +6% | Avoid euphoric spikes |
| Liquidity (median traded value 20d) | >= 50,000,000 (approx. INR 5 Cr) | Tradability guardrail |

### Intraday breakout profile (`intraday_breakout`)
Used when `is_eod` is false and the symbol is not yet in the candidate pool.

| Gate | Rule (default) | Purpose |
| --- | --- | --- |
| Starter score | >= 65 (uses score if starter_score is absent) | Fast quality bar |
| 52W proximity % | >= -8% | Stay near highs |
| Intraday RelVol | >= 1.5x | Demand live participation |
| ADX14 | >= 22 | Trend strength |
| ATR% (10d) | Between 2% and 8% | Tradable volatility band |
| Day % change | <= +5% | Avoid intraday chasing |
| Liquidity (median traded value 20d) | >= 50,000,000 | Tradability guardrail |
| Persistence | Above VWAP, cleared prior-day high, >=30 min since open, avoid lunch window | Avoid shaky breakouts |

### Candidate pool intraday overrides (for pool members only)
When a symbol is already in the pool and evaluated intraday, the profile is cloned with lighter persistence to reduce churn:
- Intraday RelVol floor relaxed to 1.2x.
- Persistence: still requires above VWAP, but drops prior-day-high requirement, removes the lunch window block, and removes the 30-minute delay (min_minutes_since_open = 0).

### `reason_parts` and `reasons_inline`
`evaluate_buy_gate` returns a short inline summary built from the checks that passed. Examples:
- EOD: `Score 74; RelVol20 1.8x; ADX14 26; ATR% 4.2; near 52W; Liquid; Day +2.3%`
- Intraday: `Starter 66; IntrRelVol 1.6x; ADX14 23; 52W -5.0%; ATR% 3.4; Liquid; Persistence ok; Day +1.8%`

## Candidate pool (strict entry, relaxed exits)

- Entry: only symbols with `buy_flag=True` on the EOD snapshot are added. `added_at`, `added_as_of`, and `added_run_id` are captured from that run.
- Ranking & size: max 10 entries; rank score weights = score 0.4, R-multiple 0.3, ADX14 0.2, 52W proximity 0.1. Extras beyond max size are marked `replaced`.
- Intraday handling: pool members are evaluated every run (using the overrides above when intraday). Status surfaces as `strong` (all good), `weakening` (warnings), or `exit_soon` (some checks currently failing). They are only removed on the next EOD snapshot.
- Exit checks (relaxed): evaluated for every member; actual removal happens only on EOD runs when any fails.
  - Above EMA20 (if price/EMA available); otherwise treated as passed.
  - ADX14 >= 18.
  - 52W proximity >= -15%.
  - Age <= 7 days since added.
- Effects of failures: 
  - During the day: status becomes `exit_soon` but the row stays in the pool.
  - On EOD sync: any failed check triggers removal and records `exit_reason` (`ema20`, `adx14`, `prox52w`, `age`, or `replaced`).

## Config source of truth
- YAML: `configs/default.yaml` (`rules.pre_gates`, `profiles.buy.swing_eod`, `profiles.buy.intraday_breakout`, `candidate_pool.*`).
- Models and defaults: `backend/app/core/config.py` (`StrategyBuyProfileConfig`, `CandidatePoolConfig`).
- Candidate pool logic: `backend/app/services/candidate_pool_service.py` (entry/ranking/exit) and `backend/app/services/buy_logic/reasoning.py` (pool intraday overrides and `reason_parts`).
