from __future__ import annotations

from datetime import date, datetime
import math
from pathlib import Path
import re
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from app.repos.parquet import datasets
from app.services.top_movers_service import ReturnRow, rank_returns


_AS_OF_DIR = re.compile(r"^as_of=(\d{4}-\d{2}-\d{2})$")


def resolve_snapshot_dates(
    daily_root: Path,
    requested_start: date,
    requested_end: date,
    *,
    latest_two: bool,
) -> tuple[date, date] | None:
    available: set[date] = set()
    if daily_root.is_dir():
        for child in daily_root.iterdir():
            if not child.is_dir():
                continue
            match = _AS_OF_DIR.fullmatch(child.name)
            if match is None:
                continue
            try:
                snapshot_date = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if snapshot_date <= requested_end:
                available.add(snapshot_date)

    ordered = sorted(available)
    if len(ordered) < 2:
        return None
    if latest_two:
        return ordered[-2], ordered[-1]

    starts = [snapshot_date for snapshot_date in ordered if snapshot_date >= requested_start]
    if not starts:
        return None
    start = starts[0]
    end = ordered[-1]
    return (start, end) if start < end else None


def _newest_run_files(daily_root: Path, snapshot_date: date) -> list[Path]:
    partition = daily_root / f"as_of={snapshot_date.isoformat()}"
    runs = sorted(
        child
        for child in partition.glob("run_id=*")
        if child.is_dir() and child.name.startswith("run_id=")
    )
    if not runs:
        return []
    return sorted(path for path in runs[-1].rglob("*.parquet") if path.is_file())


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _valid_price(value: object) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def load_score_snapshot_returns(
    symbols: Iterable[str],
    requested_start: date,
    requested_end: date,
    *,
    latest_two: bool = False,
) -> list[ReturnRow]:
    wanted = set(symbols)
    if not wanted:
        return []

    daily_root = datasets.get_parquet_root() / "scores" / "daily"
    boundaries = resolve_snapshot_dates(
        daily_root, requested_start, requested_end, latest_two=latest_two
    )
    if boundaries is None:
        return []

    file_dates: dict[Path, date] = {}
    for boundary in boundaries:
        files = _newest_run_files(daily_root, boundary)
        if not files:
            return []
        file_dates.update((path.resolve(), boundary) for path in files)

    files = sorted(file_dates)
    price_rows: list[dict[str, object]] = []
    for path in files:
        columns = set(pq.read_schema(path).names)
        if "symbol" not in columns or not ({"last", "close"} & columns):
            continue
        projection = [
            name for name in ("symbol", "last", "close", "as_of") if name in columns
        ]
        table = pq.ParquetFile(path).read(columns=projection)
        source_date = file_dates[path]
        has_last = "last" in columns
        for record in table.to_pylist():
            symbol = record.get("symbol")
            if symbol is None or str(symbol) not in wanted:
                continue
            row_as_of = record.get("as_of")
            row_date = _as_date(row_as_of) if row_as_of is not None else source_date
            if row_date != source_date:
                continue
            last = record.get("last") if has_last else None
            price = _valid_price(record.get("close") if last is None else last)
            if price is None:
                continue
            price_rows.append({"symbol": str(symbol), "dt": row_date, "close": price})

    return rank_returns(
        pa.Table.from_pylist(price_rows),
        wanted,
        boundaries[0],
        boundaries[1],
    )
