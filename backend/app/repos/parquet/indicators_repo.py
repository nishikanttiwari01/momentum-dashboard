# backend/app/repos/parquet/indicators_repo.py
from __future__ import annotations
from typing import Optional
import pyarrow as pa
import pandas as pd

from app.repos.parquet import datasets

# We store per-run indicator panels (optionally a row per [symbol, date]).
# This dataset is optional but very useful for the Drawer and for debugging.
DATASET = "indicators"


def write(run_id: str, frame: pd.DataFrame, schema_version: int = 1) -> str:
    """
    Persist a per-run indicators table.

    Input:
      - frame: pandas DataFrame. If the index is a MultiIndex [symbol, date],
               we'll flatten it into columns before writing.
      - Expected columns (examples): rsi14, adx14, ema10/50/200, atr_pct, relvol20,
               proximity_52w_high_pct, ret_1m/3m/6m/12_1m, pct_today, wk_change, wk_change_pct, etc.

    Output:
      - absolute path of the written run snapshot for convenience.
    """
    # If caller passed a MultiIndex like [symbol, date], flatten it so columns include both.
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()  # columns now include "symbol", "date", ...

    # Convert to Arrow for parquet writer (keeps types + is fast)
    table = pa.Table.from_pandas(frame, preserve_index=False)

    # Record/refresh schema version for this dataset so readers can branch on it later.
    datasets.write_schema_version(DATASET, schema_version)

    # Atomic write: tmp/part-*.parquet → commit with _SUCCESS + rowcount.txt
    w = datasets.begin_atomic_write(DATASET, run_id)
    try:
        w.write_df(table)
        w.commit()
    except Exception:
        # On any failure, try to abort (cleanup tmp) and re-raise
        try:
            w.abort()
        except Exception:
            pass
        raise

    # Return absolute path to the snapshot directory for convenience/trace
    return str((datasets.get_parquet_root() / DATASET / f"run_id={run_id}").resolve())


def read_one(symbol: str, run_id: str) -> Optional[pd.DataFrame]:
    """
    Read all indicator rows for a given symbol in a run (may include multiple dates if written as a panel).
    Returns a pandas DataFrame or None if not found.
    """
    tab = datasets.scan(DATASET, run_id=run_id, columns=None)
    if tab.num_rows == 0 or "symbol" not in tab.column_names:
        return None

    # Filter on the Arrow side first for efficiency
    import pyarrow.compute as pc
    t2 = tab.filter(pc.equal(tab["symbol"], symbol))
    if t2.num_rows == 0:
        return None

    return t2.to_pandas()


# -----------------------------------------------------------------------------
# Back-compat convenience class:
# Some callers import `IndicatorsRepo` (class) instead of the functional API.
# Provide a thin wrapper so existing imports keep working without changing call sites.
# -----------------------------------------------------------------------------

class IndicatorsRepo:
    """
    Thin convenience wrapper around the functional API in this module.
    """

    def write(self, run_id: str, frame: pd.DataFrame, schema_version: int = 1) -> str:
        """Forward to module-level write()."""
        return write(run_id=run_id, frame=frame, schema_version=schema_version)

    def read_one(self, symbol: str, run_id: str) -> Optional[pd.DataFrame]:
        """Forward to module-level read_one()."""
        return read_one(symbol=symbol, run_id=run_id)


__all__ = ["write", "read_one", "IndicatorsRepo"]
