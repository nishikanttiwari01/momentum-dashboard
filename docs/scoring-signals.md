# Scoring, Signals, and Next Actions (Enhanced)

This document expands on the **scoring and buy decision logic**, explains folder structure, and clarifies how the **`reason`** field now includes **both numerical stats and human-friendly interpretations** for each indicator.

---

## 📁 Folder Structure — Scoring Files

```
backend/app/repos/parquet/
│
├── datasets.py                # Defines datasets & partitions
├── indicators_repo.py         # Reads indicators from OHLC parquet
├── scores_repo.py             # Writes scores and related parquet outputs
│
└── scores/
    ├── daily/                 # Daily (EOD) scores — official swing-trade dataset
    │   ├── as_of=YYYY-MM-DD/
    │   │   ├── part-0000.parquet
    │   │   ├── part-0001.parquet
    │   │   └── ...
    │   └── ...
    │
    └── intraday/              # Intraday scores used for watchlists & live heatmaps
        ├── date=YYYY-MM-DD/
        │   ├── part-0000.parquet
        │   └── ...
```

**Notes:**
- The **EOD model** reads historical daily OHLC parquet files and computes indicators such as RSI, ADX, ATR10, RelVol20, and proximity to 52W high.
- Intraday parquet files are refreshed by the scheduler every 15 minutes for watchlist updates.
- **Base length (bars)** is derived from historical daily parquet — it counts how many daily bars (trading days) a stock has moved sideways before a breakout attempt.

---

## 🧮 Scoring Overview

| Pillar | Components | Weight |
|:-------|:------------|:-------|
| **Momentum** | RSI, ADX, DI+/DI−, ADX slope | 35% |
| **Breakout Quality** | 52W proximity, higher highs/lows, EMA cluster, ATR normalization | 30% |
| **Accumulation & Volume** | RelVol, OBV, CMF, volume expansion | 25% |
| **Market/Sector Context** | Index trend, sector breadth | 10% |

Final score = weighted sum of normalized 0–100 pillar scores.

### Basic Model (0–12 → %)
A lighter additive model (RSI zone + ADX band + breakout markers). Final = (points / 12) × 100.

---

## 🟢 BUY Decision Logic

**BUY = Yes** only if **all** EOD gates pass:

| Factor | Rule | Comment |
|:--------|:------|:--------|
| Score | ≥ 70 | Strong overall quality |
| 52W Proximity | ≥ −8% | Near highs |
| Pivot Clear % | Between +1% and +5% | Clean breakout, not overextended |
| Base Length | ≥ 15 bars | Mature consolidation |
| RelVol20 | ≥ 1.5× | Volume confirmation |
| ADX14 | ≥ 22 | Trend strength confirmed |
| ATR10% | Between 3–7% | Tradable volatility range |
| Day % Change | ≤ +6% | Avoid euphoric spikes |
| Liquidity | ≥ ₹5 Crore | Ensure safe tradability |

If any condition fails → **BUY = No**, with `reason` containing both **numeric stats** and **layman summary** for each metric.

---

## 🧠 `reason` Field — Format and Meaning

### ✅ Combined Format Example
```
reason: "pivot_clear:+0.3% (testing breakout) | base_len:2 (no clear base) | RelVol:0.6x (quiet, low volume) | ATR10:2.1% (low volatility) | ADX:18 (weak trend) | prox52:-12% (far from highs)"
```
Each metric is displayed as:  
**value (common-language meaning)** — making it intuitive even for non-technical readers.

### 1️⃣ Components
| Metric | Value Format | Meaning |
|:--------|:--------------|:--------|
| `pivot_clear` | % above or below breakout | Shows if stock cleared resistance (1–5% = good) |
| `base_len` | number of daily bars | Duration of sideways base (≥15 = mature) |
| `RelVol` | relative volume vs 20-day average | 1.5x+ = strong buying interest |
| `ATR10` | 10-day ATR as % of price | 3–7% = optimal volatility for swing trade |
| `ADX` | Average Directional Index | ≥22 = solid trend, <20 = weak trend |
| `prox52` | % distance from 52W high | −8% or better = near breakout zone |

### 2️⃣ Human Mapping — Range → Common Language
| Metric | Range | Meaning (for reason text) |
|:--------|:-------|:---------------------------|
| **pivot_clear %** | <0 → *(below resistance)*, 0–1 → *(testing breakout)*, 1–5 → *(clean breakout)*, >5 → *(overextended)* |
| **base_len (bars)** | <10 → *(no clear base)*, 10–14 → *(early consolidation)*, 15–25 → *(ready to break)*, >30 → *(stale setup)* |
| **RelVol** | <1.0x → *(quiet, no strong buying)*, 1.0–1.4x → *(average volume)*, 1.5–2.0x → *(strong buying)*, >2.0x → *(high-volume breakout)* |
| **ATR10 %** | <3% → *(low volatility)*, 3–7% → *(healthy tradable)*, >7% → *(too volatile)* |
| **ADX** | <20 → *(weak/sideways)*, 20–25 → *(emerging trend)*, 25–35 → *(strong trend)*, >35 → *(euphoric)* |
| **prox52 %** | <−15 → *(far from highs)*, −15–−8 → *(building base)*, −8–0 → *(near breakout zone)*, >0 → *(at highs)* |

### 3️⃣ Output Behavior
- **BUY = Yes:**
  ```
  reason: "pivot_clear:+2.4% (clean breakout) | base_len:18 (ready to break) | RelVol:1.7x (strong buying) | ATR10:4.5% (healthy volatility) | ADX:26 (strong trend) | prox52:-3% (near highs)"
  ```

- **BUY = No:**
  ```
  reason: "pivot_clear:-2.1% (below resistance) | base_len:7 (early consolidation) | RelVol:0.8x (quiet volume) | ATR10:2.3% (low volatility) | ADX:18 (weak trend) | prox52:-12% (far from highs)"
  ```

---

## 🧩 Decision Tree Summary

```
EOD Snapshot (scores/daily) → Compute Indicators
       │
       ├── score < 70 .................. → WATCH
       │
       ├── all gates pass .............. → BUY=Yes
       │
       └── any gate fails .............. → BUY=No (with reason)
```

---

## 🔍 Example Scenarios

| Situation | Indicators | Result |
|:-----------|:------------|:--------|
| Early breakout attempt | pivot_clear:+0.8% (testing breakout), base_len:8 (early consolidation), ADX:19 (weak trend), RelVol:1.0x (average) | **BUY=No** – needs more strength |
| Confirmed breakout | pivot_clear:+2.5% (clean breakout), base_len:18 (ready to break), RelVol:1.7x (strong buying), ADX:26 (strong trend), ATR:4.2% (healthy) | **BUY=Yes** – solid setup |
| Overheated run | pivot_clear:+8% (overextended), ATR:9% (too volatile), ADX:38 (euphoric) | **BUY=No** – wait for pullback |

---

## ⚙️ Configurable Parameters (default.yaml)

The BUY decision logic and several scoring thresholds are **configurable via** `config/default.yaml`. These parameters allow dynamic tuning of risk, breakout sensitivity, and volatility tolerance without code changes.

### ✅ What’s currently in your `default.yaml` (affects BUY / management)
```yaml
rules:
  breakeven_gain_pct: 5.0            # Move stop to breakeven after this gain %
  atr_chand_mult: 2.0                # Chandelier/trailing stop: ATR multiple (normal regime)
  atr_chand_mult_euphoria: 1.4       # Tighter trailing stop in euphoria
  atr_init_mult: 2.0                 # Initial stop distance on entry (in ATRs)
  euphoria:
    rsi_min: 75                      # RSI threshold for euphoria regime
    adx_min: 30                      # ADX threshold for euphoria regime
    alt_rsi_min: 70                  # Alternative RSI gate if ADX is lower
    alt_adx_min: 25                  # Alternative ADX gate if RSI is higher
    adx_slope5_min: 0                # ADX must be rising over last 5 bars
  soft_gates:                        # Pre-filters before BUY logic is applied
    min_score: 35
    min_relvol20: 0.8
    min_adx14: 22
    min_prox52w_pct: -10
    require_base_len_bars: 15
    breakout_overrides_soft_gates: true
```

**What these do:**
- `breakeven_gain_pct`, `atr_*` → **position management**, not entry; they affect **sell/stop** alerts and **trim** behavior (and will influence the narrative added to `reason` for active trades).
- `euphoria.*` → defines **overheated market**; when met, stop/trailing logic tightens and `reason` may include *"euphoric momentum"* phrasing.
- `soft_gates.*` → **pre-filters**. If these aren’t met, BUY won’t even be evaluated (you’ll see `reason` phrases like *"quiet volume"*, *"weak trend"*, *"early consolidation"* based on these thresholds).

### 🧪 Coverage check — what’s **missing** for full BUY configurability
Your BUY gates currently used by the engine include additional thresholds that are **not** present in the YAML. To make BUY fully configurable (and to keep `reason` text aligned with config), add the following keys:

```yaml
rules:
  buy:
    score_min: 70                    # Overall quality floor for BUY
    prox52w_min_pct: -8              # Must be within -8% of 52W high
    pivot_clear_min_pct: 1.0         # Breakout must clear pivot by at least 1%
    pivot_clear_max_pct: 5.0         # But not be overextended beyond 5%
    base_len_min_bars: 15            # Mature base requirement
    relvol20_min: 1.5                # Volume confirmation
    adx14_min: 22                    # Trend strength confirmation
    atr10_min_pct: 3.0               # Tradable volatility floor
    atr10_max_pct: 7.0               # Volatility ceiling (avoid whipsaw)
    day_change_max_pct: 6.0          # Avoid euphoric, chase-y candles
    liquidity_min_value: 50000000    # ₹5 Cr minimum traded value
    eod_only: true                   # Enforce EOD snapshot for BUY decisions
```

> **Why add these?** They are the exact numeric gates the BUY engine uses. Moving them to YAML ensures the BUY flag, alerts, and the `reason` text all come from a single, inspectable source of truth.

### 🗣 How config feeds the `reason` string
For each indicator, the renderer prints **stat** followed by **mapped language** based on the configured ranges:

- **Pivot clear** → uses `pivot_clear_min_pct` / `pivot_clear_max_pct`
  - `< 0%` → *(below resistance)*
  - `0–min%` → *(testing breakout)*
  - `min–max%` → *(clean breakout)*
  - `> max%` → *(overextended)*
- **Base length** → compares to `base_len_min_bars`
  - `< base_len_min` → *(early/immature base)*
  - `≥ base_len_min` → *(ready to break)*
- **RelVol20** → compares to `relvol20_min`
  - `< min` → *(quiet, low volume)*
  - `≥ min` → *(strong buying)*
- **ATR10%** → uses `atr10_min_pct` / `atr10_max_pct`
  - `< min` → *(low volatility)*
  - `min–max` → *(healthy tradable)*
  - `> max` → *(too volatile)*
- **ADX14** → uses `adx14_min`
  - `< min` → *(weak/sideways trend)*
  - `≥ min` → *(trend confirmed)*
- **Proximity to 52W high** → uses `prox52w_min_pct`
  - `< min` → *(far from highs / building base)*
  - `≥ min` → *(near breakout zone)*
- **Score** → uses `score_min`
  - `< min` → *(overall strength low)*
  - `≥ min` → *(quality met)*
- **Day change %** → uses `day_change_max_pct`
  - `> max` → *(too extended today)*
- **Liquidity** → compares to `liquidity_min_value`
  - `< min` → *(illiquid / avoid large slippage)*

**Example BUY=No (auto-composed):**
```
reason: "pivot_clear: +0.3% (testing breakout) | base_len: 12 (early base) | RelVol: 1.2x (average volume) | ATR10: 2.7% (low volatility) | ADX: 20 (weak trend) | prox52: -9% (near but not yet) | Score: 68 (strength slightly low)"
```

**Example BUY=Yes:**
```
reason: "pivot_clear: +2.1% (clean breakout) | base_len: 18 (ready to break) | RelVol: 1.8x (strong buying) | ATR10: 4.1% (healthy tradable) | ADX: 26 (trend confirmed) | prox52: -3% (near highs) | Score: 74 (quality met)"
```

> The **same YAML thresholds** feed both the **BUY boolean** and the **human-language tags** — so the reason is always consistent with the decision.

---

### 🧭 Implementation Guide (quick)
1. **Load config** at app start and expose a typed `BuyConfig` object.
2. Replace hard-coded thresholds in the BUY evaluator with `BuyConfig` values.
3. Pass `BuyConfig` into the `reason` renderer to map stats → language using the same ranges.
4. Include `config_version` in outputs so logs and emails indicate which YAML produced the decision.

---

### Summary
- **Scoring folder** structure clearly separates **daily (EOD)** vs **intraday** data.
- **Base_len_bars** counts daily consolidation bars from historical OHLC parquet.
- **Reason** field now shows both **stats and human-friendly meaning** side by side.
- This dual-format output makes reports self-explanatory for traders and analysts alike.

