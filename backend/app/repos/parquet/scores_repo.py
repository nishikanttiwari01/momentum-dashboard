from __future__ import annotations
from typing import Dict, Any, Iterable, List, Optional, Tuple

import pyarrow as pa
import pyarrow.compute as pc

from app.repos.parquet import datasets

# ---------------------------------------------------------------------------
# Phase-11: single dataset 'scores/' with schema_version=2
#           (no scores_v2 fallback paths)
#           Enrich name/sector from 'universe/' if missing.
# ---------------------------------------------------------------------------

def _resolve_run_id(as_of_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve (run_id, as_of) to read — we use the latest snapshot from 'scores/'.
    If you add a date→run index, you can implement <= as_of_str selection here.
    """
    rid = datasets.latest_snapshot("scores")
    as_of = None
    return rid, as_of


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
    Screener reader for Phase-11:
      - Reads from 'scores/' only (schema_version=2).
      - Enriches name/sector from universe if missing in snapshot.
      - Exposes canonical 'score' as:
            score_full if present
            else score_basic if present
            else legacy score if present
      - Keeps badges compatible.
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
        # 1) Resolve run_id against 'scores'
        rid = run_id
        resolved_as_of = None
        if not rid:
            rid, resolved_as_of = _resolve_run_id(as_of_str)
        if not rid:
            return [], 0, None, None

        # 2) Read Arrow table (full; we’ll project later)
        tab = datasets.scan("scores", run_id=rid, columns=None)  # single dataset now  :contentReference[oaicite:6]{index=6}

        # 3) Filter first (cheaper while still columnar)
        tab = _arrow_filter(tab, filters)
        total = tab.num_rows

        # 4) Capture as_of if present
        as_of_value = None
        if total > 0 and "as_of" in tab.column_names:
            try:
                as_of_value = tab["as_of"][0].as_py()
            except Exception:
                as_of_value = None

        # 5) Projection
        tab = _ensure_projection(tab, columns)

        # 6) Sort + slice
        tab = _arrow_sort_slice(tab, sort, page, per_page)

        # 7) Prepare universe enrichment map (for missing name/sector)
        uni_meta = _load_universe_meta()

        # 8) Materialize rows + aliasing/derivations
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

            out.append(row)

        if resolved_as_of is None:
            resolved_as_of = as_of_value

        return out, total, rid, resolved_as_of

    def latest_run(self) -> Tuple[Optional[str], Optional[str]]:
        """Return the latest available run_id from 'scores/'."""
        rid = datasets.latest_snapshot("scores")                          # single dataset now
        as_of = None
        return rid, as_of

    def read_one(self, *, symbol: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Return a single row for `symbol`."""
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
