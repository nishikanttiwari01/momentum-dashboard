from __future__ import annotations
from typing import Dict, Any, Iterable, List, Optional, Tuple

import pyarrow as pa
import pyarrow.compute as pc

from app.repos.parquet import datasets


def _resolve_run_id(as_of_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    If as_of_str is provided (YYYY-MM-DD), pick the latest run_id <= that date.
    For Phase 7 MVP, we’ll just return latest (no date index yet). We still return (run_id, as_of).
    """
    rid = datasets.latest_snapshot("scores")
    # Phase 9: map as_of->rid using a runs index; for now, resolve to latest.
    as_of = None
    return rid, as_of


def _arrow_filter(tab: pa.Table, filters):
    """
    Build a boolean mask using pyarrow.compute on *arrays*, then filter the table.
    Supported ops: gte, gt, lte, lt, in, like (prefix), eq.
    """
    if tab.num_rows == 0 or not filters:
        return tab

    mask = None

    for (field, op), val in filters.items():
        if field not in tab.column_names:
            continue
        col = tab[field]  # work with column arrays

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
            if s.endswith("%"):
                cur = pc.starts_with(col, pa.scalar(s[:-1]))
            else:
                cur = pc.equal(col, pa.scalar(s))
        elif op == "eq":
            cur = pc.equal(col, pa.scalar(val))

        if cur is not None:
            mask = cur if mask is None else pc.and_kleene(mask, cur)

    if mask is None:
        return tab
    return tab.filter(mask)


def _arrow_sort_slice(tab: pa.Table, sort: str, page: int, per_page: int) -> pa.Table:
    """
    Arrow 17: Table.sort_by accepts list of tuples: [("col", "ascending"|"descending")].
    """
    if tab.num_rows == 0:
        return tab

    keys = []
    for piece in (sort or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if piece.endswith(".desc"):
            keys.append((piece[:-5], "descending"))
        elif piece.endswith(".asc"):
            keys.append((piece[:-4], "ascending"))
        else:
            keys.append((piece, "descending"))  # default desc

    if keys:
        tab = tab.sort_by(keys)

    offset = max(0, (page - 1) * per_page)
    return tab.slice(offset, per_page)


def _synthesize_badges(row: Dict[str, Any]) -> List[Dict[str, str]]:
    badges: List[Dict[str, str]] = []
    # If parquet has booleans like 'breakout', 'near_uc', map to badge objects.
    if row.get("breakout") is True:
        badges.append({"key": "breakout", "label": "Breakout", "color": "green"})
    if row.get("near_uc") is True:
        badges.append({"key": "near_uc", "label": "Near UC", "color": "orange"})
    # You can add more mappings later (e.g., 'overbought', 'new_high', etc.)
    return badges


class ScoresRepo:
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
        # Resolve run id
        rid = run_id
        resolved_as_of = None
        if not rid:
            rid, resolved_as_of = _resolve_run_id(as_of_str)

        if not rid:
            return [], 0, None, None

        # Read table (projection for speed)
        tab = datasets.scan("scores", run_id=rid, columns=None)  # read all; filter/projection below

        # Filter
        tab = _arrow_filter(tab, filters)

        total = tab.num_rows

        # Capture as_of before projection (if present)
        as_of_value = None
        if total > 0 and "as_of" in tab.column_names:
            try:
                as_of_value = tab["as_of"][0].as_py()
            except Exception:
                as_of_value = None

        # Projection: ensure required columns exist; fill missing with nulls
        if columns:
            available = set(tab.column_names)
            needed = []
            for c in columns:
                if c in available:
                    needed.append(c)
                else:
                    # materialize a null column to keep schema stable
                    tab = tab.append_column(c, pa.nulls(total))
                    needed.append(c)
            tab = tab.select(needed)

        # Sort + slice
        tab = _arrow_sort_slice(tab, sort, page, per_page)

        # Materialize to Python dicts
        out: List[Dict[str, Any]] = []
        arrays = {name: tab[name] for name in tab.column_names}
        for i in range(tab.num_rows):
            row = {name: arrays[name][i].as_py() for name in tab.column_names}

            # Ensure ret_1w exists even if parquet lacks it (Phase 9 will populate)
            if "ret_1w" not in row:
                row["ret_1w"] = None

            # Phase7: derive 1-week fields if missing (wk_change & wk_change_pct)
            if row.get("wk_change") is None or row.get("wk_change_pct") is None:
                last = row.get("last")
                ret_1w = row.get("ret_1w")  # percent
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

            # Keep existing badges if present; otherwise synthesize
            if "badges" in row and row["badges"]:
                pass
            else:
                row["badges"] = _synthesize_badges(row)

            out.append(row)

        # If as_of wasn’t resolved from run-index, use captured value (if any)
        if resolved_as_of is None:
            resolved_as_of = as_of_value

        return out, total, rid, resolved_as_of

    # ---- Phase 8: tiny helpers needed by the Detail service ----

    def latest_run(self) -> Tuple[Optional[str], Optional[str]]:
        """Return the latest available run_id for 'scores' (and as_of if tracked)."""
        rid = datasets.latest_snapshot("scores")
        as_of = None
        return rid, as_of

    def read_one(self, *, symbol: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Return a single row for `symbol` from the given `run_id`."""
        tab = datasets.scan("scores", run_id=run_id, columns=None)
        if "symbol" not in tab.column_names:
            return None
        t2 = tab.filter(pc.equal(tab["symbol"], symbol))
        if t2.num_rows == 0:
            return None
        return {name: t2[name][0].as_py() for name in t2.column_names}
