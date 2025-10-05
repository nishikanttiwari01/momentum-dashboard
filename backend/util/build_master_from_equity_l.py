
import pandas as pd
import requests
import io
import sys
from pathlib import Path

# Usage: python build_master_from_equity_l.py /path/to/nse_master.csv
# It will update company_name using NSE's EQUITY_L.csv for all symbols it finds.

url_candidates = [
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://www.nseindia.com/content/equities/EQUITY_L.csv",
]

def download_equity_l():
    last_err = None
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,*/*;q=0.8",
        "Referer": "https://www.nseindia.com/"
    }
    for url in url_candidates:
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return pd.read_csv(io.BytesIO(r.content))
        except Exception as e:
            last_err = e
    raise SystemExit(f"Failed to download EQUITY_L.csv: {last_err}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python build_master_from_equity_l.py /path/to/nse_master.csv")
        sys.exit(2)
    master_path = Path(sys.argv[1])
    master = pd.read_csv(master_path)
    equity_l = download_equity_l()

    # Normalize columns
    equity_l.columns = [c.strip().upper().replace(" ", "_") for c in equity_l.columns]
    # Expected columns: SYMBOL, NAME_OF_COMPANY
    if "SYMBOL" not in equity_l.columns or "NAME_OF_COMPANY" not in equity_l.columns:
        raise SystemExit("EQUITY_L.csv format unexpected — SYMBOL/NAME OF COMPANY missing")

    name_map = dict(zip(equity_l["SYMBOL"].astype(str).str.upper(), equity_l["NAME_OF_COMPANY"].astype(str)))

    def strip_ns(s):
        return s[:-3] if s.upper().endswith(".NS") else s

    # Update company_name for exact symbol core match
    master["company_name"] = master["symbol"].apply(lambda s: name_map.get(strip_ns(str(s).strip().upper()), ""))                                               .where(master["company_name"].notna() & (master["company_name"].str.len() > 0),
                                                  master["company_name"])
    master.to_csv(master_path, index=False, encoding="utf-8-sig")
    print(f"Updated company_name for {master['company_name'].ne('').sum()} rows")

if __name__ == "__main__":
    main()
