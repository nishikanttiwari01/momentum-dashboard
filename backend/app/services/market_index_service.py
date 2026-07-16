from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import yfinance as yf
from pydantic import BaseModel, ConfigDict


INDEXES = {
    "sensex": ("Sensex", "^BSESN"),
    "sp500": ("S&P 500", "^GSPC"),
}
RANGES = {"1m": "1mo", "6m": "6mo", "1y": "1y", "5y": "5y"}


class MarketIndexUnavailable(RuntimeError):
    """Raised when an upstream source cannot provide usable index history."""


class MarketIndexPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    on: date
    close: float


class MarketIndexHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    symbol: str
    range: str
    latest_value: float
    change: float
    change_pct: float
    points: list[MarketIndexPoint]


HistoryLoader = Callable[[str, str], Any]


def _yahoo_history_loader(symbol: str, period: str) -> pd.DataFrame:
    return yf.Ticker(symbol).history(
        period=period,
        interval="1d",
        auto_adjust=False,
        actions=False,
    )


class MarketIndexService:
    def __init__(self, loader: HistoryLoader = _yahoo_history_loader) -> None:
        self._loader = loader

    def build_history(self, key: str, range_: str) -> MarketIndexHistory:
        if key not in INDEXES:
            raise ValueError(f"unknown market index: {key}")
        if range_ not in RANGES:
            raise ValueError(f"unsupported market index range: {range_}")

        name, symbol = INDEXES[key]
        try:
            history = self._loader(symbol, RANGES[range_])
        except Exception as exc:
            raise MarketIndexUnavailable(f"history unavailable for {key}") from exc

        points = self._normalize_points(history)
        if not points:
            raise MarketIndexUnavailable(f"history unavailable for {key}")

        first = points[0].close
        latest = points[-1].close
        change = latest - first
        change_pct = (change / first * 100.0) if first != 0 else 0.0
        return MarketIndexHistory(
            key=key,
            name=name,
            symbol=symbol,
            range=range_,
            latest_value=latest,
            change=change,
            change_pct=change_pct,
            points=points,
        )

    @staticmethod
    def _normalize_points(history: Any) -> list[MarketIndexPoint]:
        if history is None or not isinstance(history, pd.DataFrame) or history.empty:
            return []
        if "Close" not in history.columns:
            return []

        points: list[MarketIndexPoint] = []
        for raw_on, raw_close in history["Close"].items():
            try:
                close = float(raw_close)
                timestamp = pd.Timestamp(raw_on)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(close) or pd.isna(timestamp):
                continue
            points.append(MarketIndexPoint(on=timestamp.date(), close=close))

        points.sort(key=lambda point: point.on)
        return points
