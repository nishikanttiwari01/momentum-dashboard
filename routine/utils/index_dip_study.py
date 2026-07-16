"""Index mean-reversion study: is buying Nifty/BankNifty dips a measurable edge?

Motivated by real NIFTYBEES trades (buy weakness, sell the bounce in days).
Downloads full index history via yfinance and measures every dip-buy rule
honestly: entry at signal-day close, exits at +3/5/10 trading days and at
first up-close (max 10 TD). Costs on ETFs ~0.1%/round trip are noted but not
subtracted; mentally subtract them.

Run on the host machine (yfinance needs internet):
    python -m routine.utils.index_dip_study
Writes routine/reports/index_dip_study.csv and prints the table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config

SYMBOLS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}
START = "2007-01-01"
COST_NOTE = "ETF round trip ~0.1% (brokerage+slippage); subtract from every mean."


def rsi(c: pd.Series, n: int = 2) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def first_up_exit(c: np.ndarray, max_hold: int = 10) -> list:
    out = []
    for i in range(len(c)):
        val = np.nan
        for j in range(i + 1, min(i + max_hold + 1, len(c))):
            if c[j] > c[i]:
                val = c[j] / c[i] * 100 - 100
                break
        else:
            if i + max_hold < len(c):
                val = c[i + max_hold] / c[i] * 100 - 100
        out.append(val)
    return out


def build(c: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"c": c})
    df["rsi2"] = rsi(c, 2)
    df["ret1"] = c.pct_change() * 100
    df["down3"] = (df["ret1"] < 0) & (df["ret1"].shift(1) < 0) & (df["ret1"].shift(2) < 0)
    df["down4"] = df["down3"] & (df["ret1"].shift(3) < 0)
    df["ret5"] = c.pct_change(5) * 100
    df["ma20"] = c.rolling(20).mean()
    df["stretch20"] = (c / df["ma20"] - 1) * 100
    df["ma200"] = c.rolling(200).mean()
    df["above200"] = c > df["ma200"]
    for h in (3, 5, 10):
        df[f"fwd{h}"] = c.shift(-h) / c * 100 - 100
    df["fwd_firstup"] = first_up_exit(c.values)
    return df


def stats(g: pd.DataFrame, name: str, index: str, years: float) -> dict:
    out = {"index": index, "rule": name, "n": len(g), "trades_per_year": round(len(g) / years, 1)}
    if len(g) == 0:
        return out
    for col, label in (("fwd3", "3d"), ("fwd5", "5d"), ("fwd10", "10d"), ("fwd_firstup", "first_up")):
        v = g[col].dropna()
        if len(v):
            out[f"{label}_mean_pct"] = round(float(v.mean()), 2)
            out[f"{label}_win_pct"] = round(float((v > 0).mean() * 100), 0)
    out["worst_5d_pct"] = round(float(g["fwd5"].min()), 1)
    return out


def rules(df: pd.DataFrame):
    yield "BASELINE all days", df
    yield "RSI2<5", df[df["rsi2"] < 5]
    yield "RSI2<10", df[df["rsi2"] < 10]
    yield "RSI2<20", df[df["rsi2"] < 20]
    yield "3 down days", df[df["down3"]]
    yield "4 down days", df[df["down4"]]
    yield "5d ret < -2%", df[df["ret5"] < -2]
    yield "5d ret < -3%", df[df["ret5"] < -3]
    yield ">2% below 20DMA", df[df["stretch20"] < -2]
    yield "RSI2<10 & ABOVE 200DMA", df[(df["rsi2"] < 10) & df["above200"]]
    yield "RSI2<10 & BELOW 200DMA", df[(df["rsi2"] < 10) & ~df["above200"]]
    yield "3 down days & ABOVE 200DMA", df[df["down3"] & df["above200"]]
    yield "3 down days & BELOW 200DMA", df[df["down3"] & ~df["above200"]]


def main() -> int:
    import yfinance as yf

    rows = []
    for index, ticker in SYMBOLS.items():
        raw = yf.download(ticker, start=START, progress=False, auto_adjust=False)
        if raw is None or raw.empty:
            print(f"!! no data for {ticker}")
            continue
        close = raw["Close"]
        if hasattr(close, "columns"):  # multi-index columns from yfinance
            close = close.iloc[:, 0]
        c = pd.to_numeric(close, errors="coerce").dropna()
        years = max((c.index[-1] - c.index[0]).days / 365.25, 0.1)
        print(f"\n=== {index} ({ticker}): {len(c)} days, {c.index[0].date()} -> {c.index[-1].date()} ===")
        df = build(c)
        for name, g in rules(df):
            s = stats(g.dropna(subset=["fwd5"]), name, index, years)
            rows.append(s)
            m5 = s.get("5d_mean_pct")
            w5 = s.get("5d_win_pct")
            fu = s.get("first_up_mean_pct")
            fw = s.get("first_up_win_pct")
            print(f"{name:28s} n={s['n']:>4} (~{s['trades_per_year']:>4}/yr)  "
                  f"5d {m5 if m5 is not None else '—':>6}% win {w5 if w5 is not None else '—':>3}%  "
                  f"first-up {fu if fu is not None else '—':>6}% win {fw if fw is not None else '—':>3}%  "
                  f"worst5d {s.get('worst_5d_pct', '—')}%")
    out = config.reports_dir() / "index_dip_study.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nsaved: {out}")
    print(f"NOTE: {COST_NOTE}")
    print("Read the ABOVE/BELOW 200DMA split before believing any rule: "
          "dip-buying and regime interact strongly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
