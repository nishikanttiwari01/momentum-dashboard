#!/usr/bin/env python
"""
Generate an NDJSON symbol master for all NSE symbols.

- Uses nsetools to obtain the full symbol universe (~2000+).
- Uses nsepython/nsefetch to pull per-symbol metadata.

Each line = one JSON object:
{
  "symbol": "INFY",
  "companyName": "Infosys Limited",
  "industry": "IT Services & Consulting",
  "isin": "INE009A01021",
  "activeSeries": ["EQ"]
}
"""

import csv
import json
import sys
import time
import argparse
from pathlib import Path
from typing import Iterable, Dict, Any, List

from nsepython import nsefetch
try:
    from nsetools import Nse  # for full symbol list (~2000+)
except Exception:  # pragma: no cover
    Nse = None  # type: ignore


MASTER_URL = "https://www.nseindia.com/api/master-quote"  # retained for compatibility (not used for listing)
QUOTE_URL_TEMPLATE = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"
PRESETS_DIR = Path(__file__).resolve().parents[1] / "app" / "assets" / "presets"
DEFAULT_PRESET_NDJSON = PRESETS_DIR / "nse_master.ndjson"
DEFAULT_SYMBOLS_CSV = Path(__file__).resolve().parents[2] / "configs" / "nse_master.csv"


def _load_symbols_from_csv(path: Path) -> List[str]:
    """Best-effort loader for a CSV whose first column or 'symbol' column has tickers."""
    if not path.exists():
        return []
    symbols: List[str] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                return []
            header = [h.strip().lower() for h in rows[0]]
            has_header = "symbol" in header
            start_idx = header.index("symbol") if has_header else 0
            data_rows = rows[1:] if has_header else rows
            for row in data_rows:
                if not row:
                    continue
                sym = str(row[start_idx]).strip().upper()
                if sym:
                    symbols.append(sym)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] failed to load symbols from {path}: {e}", file=sys.stderr)
        return []
    return symbols


def get_all_symbols() -> Dict[str, str]:
    """
    Return {symbol: company_name} for the full NSE universe.
    Uses nsetools.get_stock_codes(); does NOT fall back to partial master-quote.
    """
    codes: Dict[str, str] = {}
    if Nse is not None:
        try:
            nse = Nse()
            codes = nse.get_stock_codes() or {}
            codes.pop("SYMBOL", None)  # header row
        except Exception as e:  # noqa: BLE001
            print(f"[warn] nsetools get_stock_codes failed: {e}", file=sys.stderr)
    return codes


def write_symbols_csv(path: Path, codes: Dict[str, str]) -> None:
    """Persist symbols (and optional company names) to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "company_name"])
        for sym, name in codes.items():
            writer.writerow([sym, name])
    print(f"[info] symbols written to {path}", file=sys.stderr)


def fetch_quote(symbol: str) -> Dict[str, Any]:
    """Fetch detailed quote for a given symbol."""
    url = QUOTE_URL_TEMPLATE.format(symbol=symbol)
    return nsefetch(url)


def build_record(symbol: str, name_from_list: str, quote: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Combine symbol list data + quote-equity details into a single record
    with the fields we care about.
    """
    company_name = name_from_list
    industry = None
    isin = None
    active_series: list[str] = []

    if quote:
        info = quote.get("info", {}) or {}

        company_name = info.get("companyName") or company_name
        industry = info.get("industry") or industry
        isin = info.get("isin") or isin

        # securityWiseDP can be list of series entries
        sec_dp = quote.get("securityWiseDP")
        if isinstance(sec_dp, list) and sec_dp:
            series_set = {row.get("series") for row in sec_dp if row.get("series")}
            active_series = sorted(series_set)

    return {
        "symbol": symbol,
        "companyName": company_name,
        "industry": industry,
        "isin": isin,
        "activeSeries": active_series,
    }


def generate_symbol_master_ndjson(
    sleep_sec: float = 0.25,
    max_symbols: int | None = None,
    symbols_override: List[str] | None = None,
    names_map: Dict[str, str] | None = None,
) -> Iterable[Dict[str, Any]]:
    """
    Yield records for all symbols as dicts (one per symbol).

    You can stream these to stdout or a file as NDJSON.
    """
    if symbols_override:
        symbols = symbols_override
        if isinstance(names_map, list):
            names = {s: "" for s in names_map if s}
        elif isinstance(names_map, dict):
            names = names_map
        else:
            names = {s: "" for s in symbols_override}
    else:
        codes = get_all_symbols()
        symbols = list(codes.keys())
        names = codes
        if not symbols:
            print("[error] no symbols resolved from nsetools; aborting", file=sys.stderr)
            return

    if max_symbols is not None:
        symbols = symbols[:max_symbols]

    for idx, symbol in enumerate(symbols, start=1):
        name_from_list = (names or {}).get(symbol, "")

        quote = None
        try:
            quote = fetch_quote(symbol)
        except Exception as e:  # noqa: BLE001
            # If quote fails, we still emit a record with whatever we have
            print(
                f"WARNING: failed to fetch quote for {symbol}: {e}",
                file=sys.stderr,
            )

        record = build_record(symbol, name_from_list, quote)
        yield record

        # Basic throttling to avoid NSE rate-limits
        time.sleep(sleep_sec)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate NSE symbol master as NDJSON."
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path (default: stdout)",
        default=None,
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.25,
        help="Sleep seconds between NSE requests (default: 0.25)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Limit number of symbols (for testing). Default: all.",
    )
    parser.add_argument(
        "--preset-csv",
        dest="preset_ndjson",
        default=None,
        help="Write master NDJSON to this path (default: app/assets/presets/nse_master.ndjson).",
    )
    parser.add_argument(
        "--no-preset",
        action="store_true",
        help="Skip writing the preset NDJSON output.",
    )
    parser.add_argument(
        "--symbols-file",
        default=None,
        help="Optional CSV with symbols to override/fallback (first column or 'symbol' column).",
    )
    parser.add_argument(
        "--symbols-out",
        default=None,
        help=f"Path to write the symbols CSV before NDJSON (default: {DEFAULT_SYMBOLS_CSV}).",
    )
    parser.add_argument(
        "--no-symbols-out",
        action="store_true",
        help="Skip writing the symbols CSV output.",
    )
    args = parser.parse_args(argv)

    if args.output:
        out_f = open(args.output, "w", encoding="utf-8")
        close_after = True
    else:
        out_f = sys.stdout
        close_after = False

    preset_path: Path | None = None
    preset_f = None
    if not args.no_preset:
        preset_path = Path(args.preset_ndjson) if args.preset_ndjson else DEFAULT_PRESET_NDJSON
        preset_path.parent.mkdir(parents=True, exist_ok=True)
        preset_f = preset_path.open("w", encoding="utf-8", newline="")
        print(f"[info] writing preset NDJSON to {preset_path}", file=sys.stderr)

    symbols_override: List[str] | None = None
    names_map: Dict[str, str] | None = None

    if args.symbols_file:
        symbols_override = _load_symbols_from_csv(Path(args.symbols_file))
        names_map = {s: "" for s in symbols_override}
        if symbols_override:
            print(f"[info] using symbols from {args.symbols_file} ({len(symbols_override)} symbols)", file=sys.stderr)
        else:
            print(f"[warn] symbols file empty or unreadable: {args.symbols_file}", file=sys.stderr)
            return
    else:
        names_map = get_all_symbols()
        # Normalize in case a non-dict sneaks in
        if isinstance(names_map, list):
            names_map = {s: "" for s in names_map if s}
        elif not isinstance(names_map, dict):
            names_map = {}
        symbols_override = list(names_map.keys())
        if symbols_override:
            # Persist symbols to CSV unless skipped
            if not args.no_symbols_out:
                symbols_out_path = Path(args.symbols_out) if args.symbols_out else DEFAULT_SYMBOLS_CSV
                write_symbols_csv(symbols_out_path, names_map)
        else:
            print("[error] no symbols resolved from nsetools; nothing to do", file=sys.stderr)
            return

    try:
        for record in generate_symbol_master_ndjson(
            sleep_sec=args.sleep,
            max_symbols=args.max,
            symbols_override=symbols_override,
            names_map=names_map,
        ):
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if preset_f:
                preset_f.write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        if close_after:
            out_f.close()
        if preset_f:
            preset_f.close()


if __name__ == "__main__":
    main()
