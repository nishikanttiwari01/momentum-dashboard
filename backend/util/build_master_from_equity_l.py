import csv
import io
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# Usage:
#   python build_master_from_equity_l.py               -> writes to configs/nse_master.csv
#   python build_master_from_equity_l.py /custom/path  -> override output path
#
# Produces an enriched master with columns (ticker first):
#   symbol,name_of_company,series,date_of_listing,paid_up_value,market_lot,isin_number,face_value
# Archives the previous file to configs/archive/nse_master_YYYYMMDD.csv before overwriting.

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "configs" / "nse_master.csv"
ARCHIVE_DIR = DEFAULT_OUT.parent / "archive"
ALLOWED_SERIES = {"EQ", "BE", "SM"}  # main, trade-to-trade, SME

URL_CANDIDATES = [
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://www.nseindia.com/content/equities/EQUITY_L.csv",
]


def download_equity_l() -> pd.DataFrame:
    last_err = None
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,*/*;q=0.8",
        "Referer": "https://www.nseindia.com/",
    }
    for url in URL_CANDIDATES:
        try:
            r = requests.get(url, headers=headers, timeout=45)
            r.raise_for_status()
            return pd.read_csv(io.BytesIO(r.content))
        except Exception as e:
            last_err = e
    raise SystemExit(f"Failed to download EQUITY_L.csv: {last_err}")


def normalize_symbol(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not s:
        return ""
    return s if s.endswith(".NS") else f"{s}.NS"


def build_master(out_path: Path = DEFAULT_OUT) -> Path:
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = download_equity_l()
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    required = [
        "SYMBOL",
        "NAME_OF_COMPANY",
        "SERIES",
        "DATE_OF_LISTING",
        "PAID_UP_VALUE",
        "MARKET_LOT",
        "ISIN_NUMBER",
        "FACE_VALUE",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"EQUITY_L.csv format unexpected; missing columns: {missing}")

    # Keep only allowed trading series (EQ/BE/SME)
    df = df[df["SERIES"].astype(str).str.upper().isin(ALLOWED_SERIES)]

    # Deduplicate by symbol and sort deterministically
    df["SYMBOL"] = df["SYMBOL"].astype(str)
    df = df[df["SYMBOL"].str.strip() != ""]
    df = df.drop_duplicates(subset=["SYMBOL"]).sort_values("SYMBOL")

    # Build output with normalized ticker first
    out_rows = []
    for _, row in df.iterrows():
        sym = normalize_symbol(row.get("SYMBOL", ""))
        if not sym:
            continue
        out_rows.append(
            {
                "symbol": sym,
                "name_of_company": str(row.get("NAME_OF_COMPANY", "")).strip(),
                "series": str(row.get("SERIES", "")).strip(),
                "date_of_listing": str(row.get("DATE_OF_LISTING", "")).strip(),
                "paid_up_value": str(row.get("PAID_UP_VALUE", "")).strip(),
                "market_lot": str(row.get("MARKET_LOT", "")).strip(),
                "isin_number": str(row.get("ISIN_NUMBER", "")).strip(),
                "face_value": str(row.get("FACE_VALUE", "")).strip(),
            }
        )

    if not out_rows:
        raise SystemExit("No rows produced from EQUITY_L.csv")

    out_columns = [
        "symbol",
        "name_of_company",
        "series",
        "date_of_listing",
        "paid_up_value",
        "market_lot",
        "isin_number",
        "face_value",
    ]

    # Archive previous file (best-effort)
    if out_path.exists():
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d")
        archive_path = ARCHIVE_DIR / f"{out_path.stem}_{stamp}{out_path.suffix}"
        try:
            shutil.copy2(out_path, archive_path)
            print(f"Archived previous master -> {archive_path}")
        except Exception as exc:
            print(f"[WARN] Could not archive previous file: {exc}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_columns)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} rows to {out_path}")
    return out_path


def main(argv=None):
    args = argv or sys.argv[1:]
    out_path = DEFAULT_OUT
    if args:
        try:
            out_path = Path(args[0])
        except Exception:
            print(f"[WARN] Invalid output path '{args[0]}', using default {DEFAULT_OUT}")
            out_path = DEFAULT_OUT

    try:
        build_master(out_path)
    except SystemExit as e:
        # bubble up SystemExit as non-zero exit
        raise
    except Exception as exc:
        print(f"[ERROR] Failed to build master: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
