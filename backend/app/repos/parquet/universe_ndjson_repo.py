# backend/app/repos/parquet/universe_ndjson_repo.py
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple, Optional

# Default NDJSON master produced by symbol_master.py
ASSETS_DIR = Path(__file__).resolve().parents[3] / "app" / "assets" / "presets"
DEFAULT_NDJSON = ASSETS_DIR / "nse_master.ndjson"

# Supported presets (single universe based on master NDJSON)
PRESETS = {"ALL"}


class UniverseNdjsonRepo:
    """
    Reads the consolidated NDJSON master (one symbol per line) and exposes the
    same interface shape as the legacy UniverseRepo.
    """

    def __init__(self, ndjson_path: Optional[Path] = None, suffix: str = ".NS"):
        self.ndjson_path = ndjson_path or DEFAULT_NDJSON
        self.suffix = suffix

    def _load_records(self) -> List[dict]:
        if not self.ndjson_path.exists():
            return []
        records: List[dict] = []
        try:
            with self.ndjson_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if isinstance(rec, dict):
                            records.append(rec)
                    except Exception:
                        continue
        except Exception:
            return []
        return records

    def list_symbols(
        self,
        preset: str,
        q: Optional[str] = None,
        page: int = 1,
        per_page: int = 1_000_000,
    ) -> Tuple[List[str], int]:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}")

        recs = self._load_records()
        symbols_raw = [str(r.get("symbol") or "").strip().upper() for r in recs if r.get("symbol")]
        symbols: List[str] = []
        for s in symbols_raw:
            if self.suffix and s and not s.endswith(self.suffix):
                symbols.append(f"{s}{self.suffix}")
            else:
                symbols.append(s)
        if q:
            qU = q.upper()
            symbols = [s for s in symbols if qU in s]

        total = len(symbols)
        start = (page - 1) * per_page
        end = start + per_page
        return symbols[start:end], total

    def list_sectors(self, preset: str) -> List[Tuple[str, int]]:
        """
        Return sector/industry counts for the preset (ALL).
        """
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}")
        recs = self._load_records()
        counts = {}
        for r in recs:
            sector = str(r.get("industry") or "UNKNOWN").strip().upper()
            counts[sector] = counts.get(sector, 0) + 1
        return sorted(counts.items(), key=lambda x: (-x[1], x[0]))
