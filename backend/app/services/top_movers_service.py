from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Iterable

import pyarrow as pa
import pyarrow.dataset as pds
from dateutil.relativedelta import relativedelta

from app.repos.parquet import datasets


@dataclass(frozen=True)
class ReturnRow:
    symbol: str
    return_pct: float
    start_date: date
    end_date: date


_WINDOWS = {
    "1d": relativedelta(days=1),
    "1w": relativedelta(weeks=1),
    "1m": relativedelta(months=1),
    "3m": relativedelta(months=3),
    "6m": relativedelta(months=6),
    "1y": relativedelta(years=1),
    "5y": relativedelta(years=5),
}


def resolve_window(
    period: str,
    end: date,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[date, date]:
    if period == "custom":
        if start_date is None or end_date is None:
            raise ValueError("custom period requires start_date and end_date")
        return start_date, end_date
    try:
        delta = _WINDOWS[period]
    except KeyError as exc:
        raise ValueError(f"unsupported period: {period}") from exc
    return end - delta, end


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


def _available_price_columns() -> set[str]:
    root = datasets.get_parquet_root() / "prices"
    return set(pds.dataset(root, format="parquet", partitioning="hive").schema.names)


def rank_returns(
    table: pa.Table,
    symbols: Iterable[str],
    requested_start: date,
    requested_end: date,
    *,
    latest_two: bool = False,
) -> list[ReturnRow]:
    wanted = set(symbols)
    points: dict[str, list[tuple[date, float]]] = {symbol: [] for symbol in wanted}
    columns = set(table.column_names)
    if not {"symbol", "dt", "close"}.issubset(columns):
        return []

    has_adjusted = "adj_close" in columns
    for record in table.to_pylist():
        symbol = str(record.get("symbol") or "")
        if symbol not in wanted:
            continue
        day = _as_date(record.get("dt"))
        if day is None or day < requested_start or day > requested_end:
            continue
        price = _valid_price(record.get("adj_close")) if has_adjusted else None
        if price is None:
            price = _valid_price(record.get("close"))
        if price is not None:
            points[symbol].append((day, price))

    result: list[ReturnRow] = []
    for symbol, history in points.items():
        if not history:
            continue
        history.sort(key=lambda point: point[0])
        if latest_two:
            history = history[-2:]
        first, last = history[0], history[-1]
        if first[0] == last[0] or first[1] == 0:
            continue
        result.append(
            ReturnRow(
                symbol=symbol,
                return_pct=(last[1] - first[1]) / first[1] * 100.0,
                start_date=first[0],
                end_date=last[0],
            )
        )
    return sorted(result, key=lambda row: (-row.return_pct, row.symbol))


def load_and_rank_returns(
    symbols: Iterable[str], start: date, end: date, *, latest_two: bool = False
) -> list[ReturnRow]:
    scan_args = {
        "run_id": None,
        "dt_range": (start.isoformat(), end.isoformat()),
    }
    try:
        available = _available_price_columns()
        columns = ["symbol", "dt", "close"]
        if "adj_close" in available:
            columns.append("adj_close")
    except Exception:
        columns = ["symbol", "dt", "close", "adj_close"]
    table = datasets.scan("prices", columns=columns, **scan_args)
    return rank_returns(table, symbols, start, end, latest_two=latest_two)
