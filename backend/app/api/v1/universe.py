# backend/app/api/v1/universe.py
from __future__ import annotations
import csv
from pathlib import Path
from typing import List, Tuple, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()

# Known presets; extend when you add more CSVs
_PRESETS = {"NIFTY50", "NIFTY100", "NIFTY500", "MIDCAP", "SMALLCAP", "ALL"}
_ASSETS_DIR = Path(__file__).resolve().parents[3] / "app" / "assets" / "presets"

# Tiny built-in fallback so tests are not blocked if CSVs aren't generated yet.
_FALLBACK = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]

class UniverseList(BaseModel):
    items: List[str]
    pagination: dict = Field(default_factory=dict)

class SectorCount(BaseModel):
    sector: str
    count: int

class SectorList(BaseModel):
    items: List[SectorCount]

def _load_csv(preset: str) -> List[str]:
    if preset not in _PRESETS:
        raise ValueError(f"unknown preset: {preset}")
    path = _ASSETS_DIR / f"{preset}.csv"
    if not path.exists():
        # CSVs not generated yet; return a small, deterministic fallback
        return list(_FALLBACK)

    try:
        with path.open("r", encoding="utf-8") as f:
            sample = f.read(1024)
            f.seek(0)
            reader = csv.reader(f)
            rows = list(reader)
    except Exception:
        return list(_FALLBACK)

    if not rows:
        return list(_FALLBACK)

    header = [h.strip().lower() for h in rows[0]]
    idx = 0
    data_rows = rows
    if "symbol" in header:
        idx = header.index("symbol")
        data_rows = rows[1:]

    syms: list[str] = []
    for row in data_rows:
        if not row:
            continue
        raw = row[idx] if idx < len(row) else ""
        sym = str(raw).strip().upper()
        if sym:
            syms.append(sym)

    return syms or list(_FALLBACK)

@router.get("/universe", response_model=UniverseList)
def get_universe(
    preset: str = Query(..., pattern="^(NIFTY50|NIFTY100|NIFTY500|MIDCAP|SMALLCAP|ALL)$"),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    items = _load_csv(preset)
    if q:
        qU = q.upper()
        items = [s for s in items if qU in s]
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]
    return UniverseList(items=page_items, pagination={"page": page, "per_page": per_page, "total": total})

@router.get("/universe/sectors", response_model=SectorList)
def get_universe_sectors(
    preset: str = Query(..., pattern="^(NIFTY50|NIFTY100|NIFTY500|MIDCAP|SMALLCAP|ALL)$"),
):
    # Until we enrich with real sectors, return a single ALL bucket with the total count.
    total = len(_load_csv(preset))
    return SectorList(items=[SectorCount(sector="ALL", count=total)])
