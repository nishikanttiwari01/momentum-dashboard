# backend/scripts/build_presets_from_nse.py
from __future__ import annotations
import io
from pathlib import Path
import requests
import pandas as pd

HERE = Path(__file__).resolve().parent
PRESETS_DIR = HERE.parent / "app" / "assets" / "presets"
PRESETS_DIR.mkdir(parents=True, exist_ok=True)

# NSE official CSV endpoints (public, no auth)
SOURCES = {
    "NIFTY50":   "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY100":  "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "NIFTY500":  "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    # Using the well-known midcap/smallcap indices for our presets:
    "MIDCAP":    "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "SMALLCAP":  "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    # ALL = entire equity master (2–3k+ stocks)
    # This file lists all active NSE equities with their series.
    "ALL":       "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
}

HEADERS = {
    # NSE may block requests without a UA/Referer
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.nseindia.com/",
}

# Series to include for ALL preset (tweak if needed)
ALL_SERIES_ALLOW = {"EQ", "BE", "SM"}  # common trading series (main, trade-to-trade, SME)

def _get_csv(url: str) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, timeout=45)
    resp.raise_for_status()
    # Try utf-8 first; fall back to ISO-8859-1 if needed
    try:
        text = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        text = resp.content.decode("iso-8859-1")
    return pd.read_csv(io.StringIO(text))

def _normalize_symbols(col: pd.Series) -> list[str]:
    return (
        col.astype(str)
           .str.strip()
           .str.upper()
           .tolist()
    )

def fetch_index_symbols(url: str) -> list[str]:
    """Handles index member lists (NIFTY50/100/500, MIDCAP, SMALLCAP)."""
    df = _get_csv(url)
    # Common header variants for the symbol column across NSE index files
    sym_col = None
    for c in df.columns:
        if str(c).strip().lower() in {"symbol", "symbol ", "symbol\n"}:
            sym_col = c
            break
    if sym_col is None:
        raise RuntimeError(f"Could not find a 'Symbol' column at {url}. Columns={list(df.columns)}")

    syms = _normalize_symbols(df[sym_col])
    syms_ns = [f"{s}.NS" for s in syms if s and s != "NAN"]
    return syms_ns

def fetch_all_equities(url: str) -> list[str]:
    """
    Handles ALL preset from EQUITY_L.csv.
    Expected columns typically include: SYMBOL, SERIES, ISIN, NAME OF COMPANY, etc.
    We keep SERIES in {EQ, BE, SM} by default.
    """
    df = _get_csv(url)

    # Resolve column names case-insensitively
    cols = {c.strip().upper(): c for c in df.columns}
    if "SYMBOL" not in cols:
        raise RuntimeError(f"'SYMBOL' column not found in ALL source. Columns={list(df.columns)}")

    symbol_col = cols["SYMBOL"]
    series_col = cols.get("SERIES")  # may exist as 'SERIES'

    # Filter by series if available
    if series_col is not None:
        df = df[df[series_col].astype(str).str.upper().isin(ALL_SERIES_ALLOW)]

    syms = _normalize_symbols(df[symbol_col])
    syms = [s for s in syms if s and s != "NAN"]

    # De-duplicate and sort for deterministic output
    syms = sorted(set(syms))

    return [f"{s}.NS" for s in syms]

def write_preset(name: str, syms: list[str]) -> Path:
    out = PRESETS_DIR / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        f.write("\n".join(syms) + "\n")
    return out

def main():
    print(f"Writing presets to: {PRESETS_DIR}")
    summary: dict[str, int] = {}

    for name, url in SOURCES.items():
        print(f" -> Fetching {name} …")
        if name == "ALL":
            syms = fetch_all_equities(url)
        else:
            syms = fetch_index_symbols(url)

        path = write_preset(name, syms)
        summary[name] = len(syms)
        print(f"    Saved {len(syms)} symbols -> {path}")

    print("\nDone.")
    for k in sorted(summary.keys()):
        print(f"{k}: {summary[k]} symbols")

if __name__ == "__main__":
    main()
