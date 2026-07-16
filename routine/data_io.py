"""Read access to the existing parquet lake (daily score snapshots).

Tolerant of schema evolution: older snapshots miss newer columns
(e.g. pre_breakout_score); missing requested columns come back as NaN.
"""
from __future__ import annotations

import glob
import logging
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
import pyarrow.parquet as pq

from . import config

log = logging.getLogger(__name__)


def list_snapshot_dates(root: Optional[Path] = None) -> List[str]:
    """Sorted ISO dates of daily partitions that actually contain parquet files.

    Empty partition dirs (weekend/holiday runs) are skipped. This list *is*
    the trading calendar used by the backtest.
    """
    base = Path(root) if root else config.scores_daily_dir()
    out: List[str] = []
    for d in sorted(base.glob("as_of=*")):
        if glob.glob(str(d / "**" / "*.parquet"), recursive=True):
            out.append(d.name.split("=", 1)[1])
    return out


def _partition_files(day: str, root: Optional[Path] = None) -> List[str]:
    base = Path(root) if root else config.scores_daily_dir()
    files = sorted(glob.glob(str(base / f"as_of={day}" / "**" / "*.parquet"), recursive=True))
    return files


def load_snapshot(
    day: str,
    columns: Optional[Iterable[str]] = None,
    root: Optional[Path] = None,
) -> pd.DataFrame:
    """Load one day's snapshot. If multiple run_ids exist, the latest wins.

    Requested columns absent from that day's schema are added as NaN so the
    caller always gets a stable frame shape.
    """
    files = _partition_files(day, root)
    if not files:
        return pd.DataFrame(columns=list(columns) if columns else None)
    # Some partitions contain partial/empty reruns; pick the file with the
    # most rows (newest wins ties).
    pf = None
    best_rows = -1
    for cand in reversed(files):
        cpf = pq.ParquetFile(cand)
        if cpf.metadata.num_rows > best_rows:
            best_rows = cpf.metadata.num_rows
            pf = cpf
    available = set(pf.schema_arrow.names)
    if columns is None:
        df = pf.read().to_pandas()
    else:
        want = [c for c in columns if c in available]
        df = pf.read(columns=want).to_pandas()
        for c in columns:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[list(columns)]
    df["as_of"] = day
    return df


def load_feature_panel(
    dates: Optional[List[str]] = None,
    columns: Optional[List[str]] = None,
    root: Optional[Path] = None,
) -> pd.DataFrame:
    """Long dataframe: one row per (as_of, symbol) with feature columns.

    De-duplicates symbols within a day (keeps last occurrence).
    """
    if dates is None:
        dates = list_snapshot_dates(root)
    if columns is None:
        columns = list(config.FEATURE_COLUMNS)
    frames = []
    for day in dates:
        try:
            df = load_snapshot(day, columns=columns, root=root)
        except Exception as exc:  # corrupt partition: skip loudly, don't die
            log.warning("skipping unreadable partition %s: %s", day, exc)
            continue
        if len(df):
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=list(columns) + ["as_of"])
    panel = pd.concat(frames, ignore_index=True)
    panel["symbol"] = panel["symbol"].astype(str).str.upper()
    panel = panel.drop_duplicates(subset=["as_of", "symbol"], keep="last")
    # Price coalescing: snapshots before ~2026-05 populate only `last`.
    if "close" in panel.columns and "last" in panel.columns:
        close_n = pd.to_numeric(panel["close"], errors="coerce")
        last_n = pd.to_numeric(panel["last"], errors="coerce")
        panel["close"] = close_n.fillna(last_n)
    return panel


def close_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    """Wide matrix of close prices: index=as_of (sorted), columns=symbol."""
    m = panel.pivot(index="as_of", columns="symbol", values="close")
    m = m.sort_index()
    m = m.apply(pd.to_numeric, errors="coerce")
    return m
