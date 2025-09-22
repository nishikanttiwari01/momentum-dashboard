from __future__ import annotations
from typing import Dict, Any, Iterable, List, Optional, Tuple

from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.compute as pc

from app.repos.parquet import datasets

# ---------------------------------------------------------------------------
# Phase-11 → Phase-12 bridge:
#   - Prefer latest INTRADAY (today) when run_id is not provided.
#   - Otherwise fall back to latest DAILY (≤ today).
#   - Else fall back to legacy 'scores/run_id=*' latest snapshot.
#   - If run_id is explicitly given, continue to read legacy 'scores' (unchanged).
#   - Enrich name/sector from 'universe/' if missing.
# ---------------------------------------------------------------------------

def _today_local_str() -> str:
    # Keep minimal dependencies: use UTC date as neutral boundary for now.
    # (If you later add a market_tz, resolve here.)
    return datetime.now(timezone.utc).date().strftime("%Y-%m-%d")


def _resolve_run_legacy(as_of_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Legacy single-dataset resolver (kept for fallback)."""
    rid = datasets.latest_snapshot("scores")
    as_of = None
    return rid, as_of


def _resolve_snapshot(as_of_str: Optional[str]) -> Tuple[str, Dict[str, str], Optional[str], Optional[str]]:
    """
    Decide which partition to read when run_id is not provided.

    Returns:
      (kind, locator, resolved_run_id, resolved_as_of)
      kind ∈ {"intraday", "daily", "legacy"}
      locator: {"date": "...", "run_id": "..."} for intraday,
               {"as_of": "..."} for daily,
               {"run_id": "..."} for legacy.
    """
    # 1) Prefer latest intraday for today
    today = _today_local_str()
    rid_intra = datasets.latest_intraday(today)
    if rid_intra:
        return "intraday", {"date": today, "run_id": rid_intra}, rid_intra, None

    # 2) Else choose latest daily at or before today
    as_of = datasets.latest_daily_at_or_before(today)
    if as_of:
        # We can return as_of; run_id is available inside the files but not required for scanning.
        return "daily", {"as_of": as_of}, None, as_of

    # 3) Else fall back to legacy
    rid_legacy, as_of_legacy = _resolve_run_legacy(as_of_str)
    if rid_legacy:
        return "legacy", {"run_id": rid_legacy}, rid_legacy, as_of_legacy

    # No data at all
    return "legacy", {"run_id": None}, None, None


def _arrow_filter(tab: pa.Table, filters: Dict[Tuple[str, str], Any]) -> pa.Table:
    """
    Build a boolean mask using pyarrow.compute on arrays, then filter the table.
    Supported ops: gte, gt, lte, lt, in, like (prefix), eq.
    Unknown fields are skipped to stay resilient to schema drift.
    """
    if tab.num_rows == 0 or not filters:
        return tab

    mask = None
    for (field, op), val in filters.items():
        if field not in tab.column_names:
            continue
        col = tab[field]
        cur = None
        if op == "gte":
            cur = pc.greater_equal(col, pa.scalar(val))
        elif op == "gt":
            cur = pc.greater(col, pa.scalar(val))
        elif op == "lte":
            cur = pc.less_equal(col, pa.scalar(val))
        elif op == "lt":
            cur = pc.less(col, pa.scalar(val))
        elif op == "in":
            cur = pc.is_in(col, value_set=pa.array(val))
        elif op == "like":
            s = str(val)
            cur = pc.starts_with(col, pa.scalar(s[:-1])) if s.endswith("%") else pc.equal(col, pa.scalar(s))
        elif op == "eq":
            cur = pc.equal(col, pa.scalar(val))

        if cur is not None:
            mask = cur if mask is None else pc.and_kleene(mask, cur)

    return tab if mask is None else tab.filter(mask)


def _arrow_sort_slice(tab: pa.Table, sort: str, page: int, per_page: int) -> pa.Table:
    """Sort and paginate. Unknown sort columns are ignored. Bare 'col' → desc."""
    if tab.num_rows == 0:
        return tab

    keys = []
    for piece in (sort or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if piece.endswith(".desc"):
            col = piece[:-5]
            if col in tab.column_names:
                keys.append((col, "descending"))
        elif piece.endswith(".asc"):
            col = piece[:-4]
            if col in tab.column_names:
                keys.append((col, "ascending"))
        else:
            col = piece
            if col in tab.column_names:
                keys.append((col, "descending"))

    if keys:
        tab = tab.sort_by(keys)

    offset = max(0, (page - 1) * per_page)
    return tab.slice(offset, per_page)


def _ensure_projection(tab: pa.Table, columns: Optional[Iterable[str]]) -> pa.Table:
    """Append null columns requested by API if missing in the Parquet snapshot."""
    if not columns:
        return tab
    total = tab.num_rows
    available = set(tab.column_names)
    needed = []
    for c in columns:
        if c in available:
            needed.append(c)
        else:
            tab = tab.append_column(c, pa.nulls(total))
            needed.append(c)
    return tab.select(needed)


def _load_universe_meta() -> Dict[str, Dict[str, Optional[str]]]:
    """
    Load latest universe snapshot and build a map:
      symbol -> {'name': str|None, 'sector': str|None}
    If no universe table is present yet, returns {}.
    """
    utab = datasets.scan("universe", run_id=None, columns=["symbol", "name", "sector"])
    meta: Dict[str, Dict[str, Optional[str]]] = {}
    if utab.num_rows == 0 or "symbol" not in utab.column_names:
        return meta
    arr_sym = utab["symbol"]
    arr_name = utab["name"] if "name" in utab.column_names else None
    arr_sec = utab["sector"] if "sector" in utab.column_names else None
    for i in range(utab.num_rows):
        sym = arr_sym[i].as_py()
        meta[sym] = {
            "name": arr_name[i].as_py() if arr_name is not None else None,
            "sector": arr_sec[i].as_py() if arr_sec is not None else None,
        }
    return meta


# Aliases from older/alternative column names to canonical Phase-11 names
_P11_ALIASES = {
    "relvol20": "relvol20",                      # kept same; present for completeness
    "proximity_52w_high_pct": "proximity_52w_high_pct",
    "pct_from_52w_high": "proximity_52w_high_pct",  # legacy → canonical
}


class ScoresRepo:
    """
    Screener reader with intraday-first, daily-fallback resolution:
      - When run_id is given → read legacy 'scores/run_id=*' (back-compat).
      - When run_id is None → prefer latest intraday (today), else latest daily (≤ today),
        else legacy latest snapshot.
      - Enriches name/sector from universe if missing in snapshot.
      - Canonicalizes 'score' and badges.
    """

    def read(
        self,
        *,
        run_id: Optional[str],
        as_of_str: Optional[str],
        filters: Dict[Tuple[str, str], Any],
        sort: str,
        page: int,
        per_page: int,
        columns: Optional[Iterable[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str], Optional[str]]:
        # 1) Resolve what to read
        resolved_as_of: Optional[str] = None

        if run_id:
            # Back-compat path: legacy single-dataset read
            tab = datasets.scan("scores", run_id=run_id, columns=None)
            rid_used = run_id
        else:
            kind, locator, rid_used, resolved_as_of = _resolve_snapshot(as_of_str)

            if kind == "intraday":
                tab = datasets.scan_scores_intraday(locator["date"], locator["run_id"], columns=None)
            elif kind == "daily":
                tab = datasets.scan_scores_daily(locator["as_of"], columns=None)
            else:
                # legacy fallback
                rid = locator.get("run_id")
                if rid is None:
                    return [], 0, None, None
                tab = datasets.scan("scores", run_id=rid, columns=None)
                rid_used = rid

            # If daily read and we can extract an embedded run_id from metadata later, we'll leave rid_used as-is.
            # For API contract we return (rid_used, resolved_as_of); rid_used may be None for daily until we inspect rows.

        # 2) Filter first
        tab = _arrow_filter(tab, filters)
        total = tab.num_rows

        # 3) Capture as_of (first row)
        as_of_value = None
        if total > 0 and "as_of" in tab.column_names:
            try:
                as_of_value = tab["as_of"][0].as_py()
            except Exception:
                as_of_value = None

        # 4) Projection
        tab = _ensure_projection(tab, columns)

        # 5) Sort + slice
        tab = _arrow_sort_slice(tab, sort, page, per_page)

        # 6) Universe enrichment
        uni_meta = _load_universe_meta()

        # 7) Materialize rows + aliasing/derivations
        out: List[Dict[str, Any]] = []
        arrays = {name: tab[name] for name in tab.column_names}
        for i in range(tab.num_rows):
            row = {name: arrays[name][i].as_py() for name in tab.column_names}

            # Normalize aliases → canonical names
            for alias, canon in _P11_ALIASES.items():
                if alias in row and canon not in row:
                    row[canon] = row.get(alias)

            # Canonical score: full → basic → legacy
            if row.get("score_full") is not None:
                row["score"] = row["score_full"]
            elif row.get("score_basic") is not None:
                row["score"] = row["score_basic"]
            # If both are None, keep whatever 'score' exists (legacy), else None

            # score_scale default
            if not row.get("score_scale"):
                row["score_scale"] = "0-100"

            # pct_today default ← change_pct when missing
            if row.get("pct_today") is None and row.get("change_pct") is not None:
                row["pct_today"] = row["change_pct"]

            # 1W derived from ret_1w if wk_* absent (preserves Phase-7 contract)
            if row.get("wk_change") is None or row.get("wk_change_pct") is None:
                last = row.get("last")
                ret_1w = row.get("ret_1w")
                wk_chg = wk_pct = None
                try:
                    if last is not None and ret_1w is not None:
                        r = float(ret_1w)
                        denom = 1.0 + (r / 100.0)
                        if denom > 0.0:
                            base = float(last) / denom
                            wk_chg = float(last) - base
                            wk_pct = r
                except Exception:
                    wk_chg, wk_pct = None, None
                row.setdefault("wk_change", wk_chg)
                row.setdefault("wk_change_pct", wk_pct)

            # Badges normalization: if not list[dict], synthesize from legacy booleans
            badges = row.get("badges")
            if not (isinstance(badges, list) and (not badges or isinstance(badges[0], dict))):
                out_b = []
                if row.get("breakout") is True:
                    out_b.append({"code": "breakout", "text": "Breakout", "color": "success"})
                if row.get("near_uc") is True:
                    out_b.append({"code": "near_uc", "text": "Near UC", "color": "warning"})
                row["badges"] = out_b

            # Enrich name/sector from universe if missing/empty
            sym = row.get("symbol")
            if sym and isinstance(sym, str):
                meta = uni_meta.get(sym)
                if meta:
                    if not row.get("name"):
                        row["name"] = meta.get("name")
                    if not row.get("sector"):
                        row["sector"] = meta.get("sector")

            # Capture run_id if we don't have one yet (daily path)
            nonlocal_rid = row.get("run_id")
            if not run_id and nonlocal_rid and not (isinstance(nonlocal_rid, float) and pa.scalar(nonlocal_rid).is_valid is False):
                # trust embedded run_id if present in rows
                rid_used = rid_used or nonlocal_rid

            out.append(row)
        # Drop rows that violate API contract (e.g., last must be a number)
        # Keeps behavior stable without touching pydantic models.
        out = [r for r in out if isinstance(r.get("last"), (int, float))]
        total = len(out)


        if resolved_as_of is None:
            resolved_as_of = as_of_value

        return out, total, rid_used, resolved_as_of

    def latest_run(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Return the latest available snapshot:
          - intraday(today) if present,
          - else daily(≤ today),
          - else legacy latest.
        """
        today = _today_local_str()
        rid_intra = datasets.latest_intraday(today)
        if rid_intra:
            return rid_intra, None

        as_of = datasets.latest_daily_at_or_before(today)
        if as_of:
            # We don't need run_id to identify daily partitions; report as_of.
            return None, as_of

        return _resolve_run_legacy(None)

    def read_one(self, *, symbol: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Return a single row for `symbol` using legacy 'scores' path (back-compat)."""
        tab = datasets.scan("scores", run_id=run_id, columns=None)
        if "symbol" not in tab.column_names or tab.num_rows == 0:
            return None
        t2 = tab.filter(pc.equal(tab["symbol"], symbol))
        if t2.num_rows == 0:
            return None
        row = {name: t2[name][0].as_py() for name in t2.column_names}

        # Canonical score normalization for read_one as well
        if row.get("score_full") is not None:
            row["score"] = row["score_full"]
        elif row.get("score_basic") is not None:
            row["score"] = row["score_basic"]
        if not row.get("score_scale"):
            row["score_scale"] = "0-100"

        # Enrich name/sector if needed
        uni_meta = _load_universe_meta()
        meta = uni_meta.get(symbol)
        if meta:
            if not row.get("name"):
                row["name"] = meta.get("name")
            if not row.get("sector"):
                row["sector"] = meta.get("sector")

        # Normalize badges
        badges = row.get("badges")
        if not (isinstance(badges, list) and (not badges or isinstance(badges[0], dict))):
            out_b = []
            if row.get("breakout") is True:
                out_b.append({"code": "breakout", "text": "Breakout", "color": "success"})
            if row.get("near_uc") is True:
                out_b.append({"code": "near_uc", "text": "Near UC", "color": "warning"})
            row["badges"] = out_b

        return row
