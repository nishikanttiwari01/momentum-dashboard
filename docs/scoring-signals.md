# Scoring, Signals, and Next Actions

This section formalizes **both** the Basic and Full scoring models, plus derived **next actions** used in the Right Drawer.

## Pillars & Weights (Full Score)

- Momentum (RSI, ADX, DI+, DI−, ADX slope): **35**
- Breakout Quality (52W proximity, recent HH/HL, close > EMA cluster, ATR% normalization): **30**
- Accumulation & Volume (RelVol, OBV/CMF proxies, down-day capitulation): **25**
- Market/Sector Context (Index trend, sector breadth): **10**

Each pillar is normalized to 0–100 via piecewise functions and capped; the **Full score** is a weighted sum.

## Basic Score (0–12 → 0–100%)

A simpler additive model across 12 points (RSI zones, ADX ranges, breakout markers). Final % = points/12 × 100.

## Entry/Stops/Lock Logic (Right Drawer)

- **Entry Suggestion:** if strong momentum AND price ≥ EMA slow → suggested near EMA fast/anchor; else wait-for-retest rule.
- **Stops:** initial stop at recent swing-low or ATR×k below entry; **breakeven** after R multiple reached.
- **Lock/Position:** persisted in `positions` table; used to compute live P/L and expose “Next action with reason.”

> Calibrate thresholds (e.g., Buy ≥ 60–65) empirically using last-year snapshots. Keep cushions to avoid intraday noise.