# backend/app/repos/parquet/scores_repo.py
from __future__ import annotations
from typing import Dict, Any, Iterable, List, Optional, Tuple

from datetime import datetime, timezone
import os
import logging
import re

import pyarrow as pa
import pyarrow.compute as pc

from app.repos.parquet import datasets

# ---------------------------------------------------------------------------
# Phase-11 → Phase-12 reader bridge (minimal changes, better logging):
#   - Prefer latest INTRADAY (today) when run_id is not provided.
#   - Otherwise fall back to latest DAILY (≤ today).
#   - Legacy fallback is NOW DISABLED by default to avoid confusion.
#       * Set ALLOW_LEGACY_SCORES_READ=1 to re-enable legacy fallback.
#   - If run_id is explicitly given, continue to read legacy 'scores/run_id=*'.
#   - Enrich name/sector from 'universe/' if missing.
#   - NEW (Oct 2025): If client sends `as_of`, honor that exact daily snapshot.
# ---------------------------------------------------------------------------

log = logging.getLogger("app.repos.parquet.scores_repo")

_RE_RUN_ID_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})")


def _run_id_to_date(run_id: str | None) -> Optional[str]:
    if not run_id:
        return None
    m = _RE_RUN_ID_DATE.match(run_id)
    if not m:
        return None
    try:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    except Exception:
        return None


_ALLOW_LEGACY_FALLBACK = os.getenv("ALLOW_LEGACY_SCORES_READ", "0").lower() in ("1", "true", "yes")

def _today_local_str() -> str:
    # Keep minimal dependencies: use UTC date as neutral boundary for now.
    # (If you later add a market_tz, resolve here.)
    return datetime.now(timezone.utc).date().strftime("%Y-%m-%d")


def _resolve_run_legacy(as_of_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Legacy single-dataset resolver (kept but gated by env toggle)."""
    rid = datasets.latest_snapshot("scores")
    as_of = None
    return rid, as_of


def _resolve_snapshot(as_of_str: Optional[str]) -> Tuple[str, Dict[str, str], Optional[str], Optional[str]]:
    """
    Decide which partition to read when run_id is not provided.

    Returns:
      (kind, locator, resolved_run_id, resolved_as_of)
      kind ∈ {"intraday", "daily", "legacy", "none"}
      locator: {"date": "...", "run_id": "..."} for intraday,
               {"as_of": "..."} for daily,
               {"run_id": "..."} for legacy,
               {} for none.
    """
    # 1) Prefer latest intraday for today
    today = _today_local_str()
    rid_intra = datasets.latest_intraday(today)
    if rid_intra:
        log.info("scores_resolve_snapshot", extra={"kind": "intraday", "date": today, "run_id": rid_intra})
        return "intraday", {"date": today, "run_id": rid_intra}, rid_intra, None

    # 2) Else choose latest daily at or before today
    as_of = datasets.latest_daily_at_or_before(today)
    if as_of:
        log.info("scores_resolve_snapshot", extra={"kind": "daily", "as_of": as_of})
        # We can return as_of; run_id is embedded in files but not required for scanning.
        return "daily", {"as_of": as_of}, None, as_of

    # 3) Else (optionally) fall back to legacy
    rid_legacy, as_of_legacy = _resolve_run_legacy(as_of_str)
    if rid_legacy and _ALLOW_LEGACY_FALLBACK:
        log.info("scores_resolve_snapshot", extra={"kind": "legacy", "run_id": rid_legacy})
        return "legacy", {"run_id": rid_legacy}, rid_legacy, as_of_legacy

    log.warning("scores_resolve_snapshot", extra={"kind": "none"})
    return "none", {}, None, None


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
      - When run_id is given → read explicit snapshot (intraday/daily, legacy as fallback).
      - When run_id is None → prefer latest intraday (today), else latest daily (≤ today).
      - Legacy fallback is disabled by default to avoid confusion (set ALLOW_LEGACY_SCORES_READ=1 to re-enable).
      - Enriches name/sector from universe if missing in snapshot.
      - Canonicalizes 'score' and badges.
      - NEW: If `as_of` is provided, always read that exact daily snapshot.
    """

    @staticmethod
    def run_id_to_date(run_id: Optional[str]) -> Optional[str]:
        return _run_id_to_date(run_id)

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
        # 0) entry log
        try:
            log.info("scores_read_begin", extra={
                "explicit_run_id": run_id, "as_of": as_of_str,
                "filters": list(filters.keys()) if filters else None,
                "sort": sort, "page": page, "per_page": per_page
            })
        except Exception:
            pass

        # 1) Resolve what to read
        resolved_as_of: Optional[str] = None
        rid_used: Optional[str] = None
        tab: pa.Table | None = None

        # --- NEW: exact daily snapshot when as_of is explicitly provided (and no run_id)
        if as_of_str and not run_id:
            try:
                log.info("scores_read_resolve", extra={"kind": "daily(explicit-as_of)", "as_of": as_of_str})
            except Exception:
                pass
            tab = datasets.scan_scores_daily(as_of_str, columns=None)
            resolved_as_of = as_of_str

        elif run_id:
            rid_used = run_id
            date_hint = _run_id_to_date(run_id)
            tab = None
            resolved_as_of = None
            if date_hint:
                try:
                    tab_candidate = datasets.scan_scores_intraday(date_hint, run_id, columns=None)
                    if tab_candidate.num_rows > 0:
                        tab = tab_candidate
                        log.info("scores_read_resolve", extra={"kind": "intraday(explicit)", "date": date_hint, "run_id": run_id})
                except Exception:
                    tab = None
                if tab is None:
                    try:
                        tab_candidate = datasets.scan_scores_daily(date_hint, columns=None)
                        if tab_candidate.num_rows > 0:
                            tab = tab_candidate
                            resolved_as_of = date_hint
                            log.info("scores_read_resolve", extra={"kind": "daily(explicit)", "as_of": date_hint, "run_id": run_id})
                    except Exception:
                        tab = None
            if tab is None:
                log.info("scores_read_resolve", extra={"kind": "legacy(explicit)", "run_id": run_id})
                tab = datasets.scan("scores", run_id=run_id, columns=None)
        else:
            kind, locator, rid_used, resolved_as_of = _resolve_snapshot(as_of_str)
            log.info("scores_read_resolve", extra={"kind": kind, "locator": locator})

            if kind == "intraday":
                tab = datasets.scan_scores_intraday(locator["date"], locator["run_id"], columns=None)
            elif kind == "daily":
                tab = datasets.scan_scores_daily(locator["as_of"], columns=None)
            elif kind == "legacy":
                rid = locator.get("run_id")
                if rid is None:
                    log.warning("scores_read_no_legacy_snapshot")
                    return [], 0, None, None
                tab = datasets.scan("scores", run_id=rid, columns=None)
                rid_used = rid
            else:
                # none
                log.warning("scores_read_no_snapshot_available")
                return [], 0, None, None

        # 2) Raw load count
        try:
            log.info("scores_read_loaded", extra={"rows": tab.num_rows, "cols": tab.column_names})
        except Exception:
            pass

        # 3) Filter first
        tab = _arrow_filter(tab, filters)
        total = tab.num_rows
        try:
            log.info("scores_read_after_filter", extra={"rows": total})
        except Exception:
            pass

        # 4) Capture as_of (first row)
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

        # 7) Universe enrichment
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

            # If both are None, keep whatever 'score' exists (legacy), else None
            # Canonical score: full → basic_normalized → basic (legacy)
            if row.get("score_full") is not None:
                row["score"] = row["score_full"]
            elif row.get("score_basic_normalized") is not None:
                row["score"] = row["score_basic_normalized"]
            elif row.get("score_basic") is not None:
                # Older snapshots may only have score_basic.
                # Treat it as canonical if it looks like a 0..100 value.
                try:
                    row["score"] = int(float(row["score_basic"]))
                except Exception:
                    pass

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
            if not run_id and isinstance(nonlocal_rid, str) and nonlocal_rid:
                rid_used = rid_used or nonlocal_rid

            out.append(row)

        # Drop rows that violate API contract (e.g., last must be a number)
        out = [r for r in out if isinstance(r.get("last"), (int, float))]
        total = len(out)

        if resolved_as_of is None:
            resolved_as_of = as_of_value

        try:
            log.info("scores_read_complete", extra={"total": total, "rid_used": rid_used, "as_of": resolved_as_of})
        except Exception:
            pass

        return out, total, rid_used, resolved_as_of

    def latest_run(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Return the latest available snapshot:
          - intraday(today) if present,
          - else daily(≤ today),
          - else (optionally) legacy latest if ALLOW_LEGACY_SCORES_READ=1.
        """
        today = _today_local_str()
        rid_intra = datasets.latest_intraday(today)
        if rid_intra:
            log.info("scores_latest_run", extra={"kind": "intraday", "date": today, "run_id": rid_intra})
            return rid_intra, None

        as_of = datasets.latest_daily_at_or_before(today)
        if as_of:
            log.info("scores_latest_run", extra={"kind": "daily", "as_of": as_of})
            # We don't need run_id to identify daily partitions; report as_of.
            return None, as_of

        rid_legacy, as_of_legacy = _resolve_run_legacy(None)
        if rid_legacy and _ALLOW_LEGACY_FALLBACK:
            log.info("scores_latest_run", extra={"kind": "legacy", "run_id": rid_legacy})
            return rid_legacy, as_of_legacy

        log.warning("scores_latest_run", extra={"kind": "none"})
        return None, None

    def read_one(self, *, symbol: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Return a single row for `symbol` using legacy 'scores' path (explicit run_id)."""
        try:
            log.info("scores_read_one_begin", extra={"symbol": symbol, "run_id": run_id})
        except Exception:
            pass

        tab = datasets.scan("scores", run_id=run_id, columns=None)
        if "symbol" not in tab.column_names or tab.num_rows == 0:
            log.warning("scores_read_one_empty", extra={"symbol": symbol, "run_id": run_id})
            return None
        t2 = tab.filter(pc.equal(tab["symbol"], symbol))
        if t2.num_rows == 0:
            log.warning("scores_read_one_not_found", extra={"symbol": symbol, "run_id": run_id})
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

        log.info("scores_read_one_ok", extra={"symbol": symbol, "run_id": run_id})
        return row
