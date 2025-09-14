# backend/app/repos/parquet/universe_repo.py
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Optional

ASSETS_DIR = Path(__file__).resolve().parents[3] / "app" / "assets" / "presets"
PRESETS = {"NIFTY50","NIFTY100","NIFTY500","MIDCAP","SMALLCAP","ALL"}

class UniverseRepo:
    """
    Reads preset CSVs (one symbol per line, uppercased, usually with .NS).
    """
    def __init__(self, assets_dir: Optional[Path] = None):
        self.assets_dir = assets_dir or ASSETS_DIR

    def _load_file(self, preset: str) -> List[str]:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}")
        p = self.assets_dir / f"{preset}.csv"
        if not p.exists():
            return []  # tolerate missing presets (dev-first)
        with p.open("r", encoding="utf-8") as f:
            return [ln.strip().upper() for ln in f if ln.strip()]

    def list_symbols(
        self,
        preset: str,
        q: Optional[str] = None,
        page: int = 1,
        per_page: int = 1000000,
    ) -> Tuple[List[str], int]:
        items = self._load_file(preset)
        if q:
            qU = q.upper()
            items = [s for s in items if qU in s]
        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        return items[start:end], total

    def list_sectors(self, preset: str) -> List[Tuple[str, int]]:
        # until we enrich by sector, return a single ALL bucket
        items = self._load_file(preset)
        return [("ALL", len(items))]
