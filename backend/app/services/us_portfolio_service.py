"""USD portfolio tracking for BUY-only US ETF positions."""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "configs" / "us_portfolio.yaml"
TRANSACTIONS_PATH = ROOT / "data" / "us_portfolio_transactions.csv"
CACHE_DIR = ROOT / "data" / "us_portfolio_cache"
FIELDS = ("id", "instrument_id", "purchased_at", "quantity", "price_usd", "fees_usd")
RANGE_DAYS = {"1m": 31, "6m": 183, "1y": 366, "5y": 1830, "max": None}


@dataclass(frozen=True)
class BuyTransaction:
    id: str
    instrument_id: str
    purchased_at: datetime
    quantity: float
    price_usd: float
    fees_usd: float = 0.0

    def validate(self) -> None:
        if self.instrument_id != "qqq":
            raise ValueError("Unsupported US instrument")
        if self.purchased_at.tzinfo is None:
            raise ValueError("Purchase time must include a timezone")
        if not math.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("Quantity must be greater than zero")
        if not math.isfinite(self.price_usd) or self.price_usd <= 0:
            raise ValueError("Price must be greater than zero")
        if not math.isfinite(self.fees_usd) or self.fees_usd < 0:
            raise ValueError("Fees cannot be negative")


class TransactionRepository:
    def __init__(self, path: Path = TRANSACTIONS_PATH):
        self.path = Path(path)

    def list_for(self, instrument_id: str) -> list[BuyTransaction]:
        if not self.path.exists():
            return []
        rows: list[BuyTransaction] = []
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("instrument_id") != instrument_id:
                    continue
                rows.append(BuyTransaction(
                    id=row["id"], instrument_id=row["instrument_id"],
                    purchased_at=datetime.fromisoformat(row["purchased_at"].replace("Z", "+00:00")),
                    quantity=float(row["quantity"]), price_usd=float(row["price_usd"]),
                    fees_usd=float(row.get("fees_usd") or 0),
                ))
        return sorted(rows, key=lambda item: item.purchased_at)

    def add(self, transaction: BuyTransaction) -> BuyTransaction:
        transaction.validate()
        existing = self.list_for(transaction.instrument_id)
        if any(row.id == transaction.id for row in existing):
            raise ValueError("Duplicate transaction id")
        all_rows = existing + [transaction]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                for item in all_rows:
                    row = asdict(item)
                    row["purchased_at"] = item.purchased_at.isoformat()
                    writer.writerow(row)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return transaction


def calculate_holding(rows: list[BuyTransaction], latest_price: float | None) -> dict[str, Any]:
    units = sum(row.quantity for row in rows)
    invested = sum(row.quantity * row.price_usd + row.fees_usd for row in rows)
    average = invested / units if units else None
    value = units * latest_price if latest_price is not None else None
    gain = value - invested if value is not None else None
    return {
        "total_units": round(units, 6),
        "total_invested_usd": round(invested, 2),
        "average_buy_price_usd": round(average, 4) if average is not None else None,
        "current_value_usd": round(value, 2) if value is not None else None,
        "unrealized_gain_usd": round(gain, 2) if gain is not None else None,
        "unrealized_gain_pct": round(gain * 100 / invested, 2) if gain is not None and invested else None,
    }


def _config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def fetch_price_history(ticker: str, force_refresh: bool = False) -> list[tuple[date, float]]:
    cfg = _config().get("us_portfolio") or {}
    ttl = float(cfg.get("price_cache_ttl_hours") or 12) * 3600
    cache = CACHE_DIR / f"{ticker.upper()}.json"
    cached = None
    try:
        if cache.exists():
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if not force_refresh and time.time() - cached["fetched_at"] < ttl:
                return [(date.fromisoformat(p["date"]), float(p["price"])) for p in cached["points"]]
    except Exception:
        cached = None
    try:
        import yfinance as yf
        frame = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=True, actions=False)
        points = [(idx.date(), float(value)) for idx, value in frame["Close"].dropna().items() if math.isfinite(float(value))]
        if points:
            payload = {"fetched_at": time.time(), "points": [{"date": d.isoformat(), "price": p} for d, p in points]}
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload), encoding="utf-8")
            return points
    except Exception:
        pass
    if cached:
        return [(date.fromisoformat(p["date"]), float(p["price"])) for p in cached.get("points", [])]
    return []


def _transaction_payload(row: BuyTransaction) -> dict[str, Any]:
    return {
        "id": row.id, "instrument_id": row.instrument_id,
        "purchased_at": row.purchased_at.isoformat(), "quantity": row.quantity,
        "price_usd": row.price_usd, "fees_usd": row.fees_usd,
        "invested_usd": round(row.quantity * row.price_usd + row.fees_usd, 2),
    }


def build_overview(force_refresh: bool = False, repo: TransactionRepository | None = None) -> dict[str, Any]:
    repo = repo or TransactionRepository()
    rows = repo.list_for("qqq")
    prices = fetch_price_history("QQQ", force_refresh)
    latest = prices[-1][1] if prices else None
    holding = calculate_holding(rows, latest)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "currency": "USD", "instruments": [{
        "id": "qqq", "ticker": "QQQ", "name": "Invesco QQQ Trust", "currency": "USD",
        "latest_price_usd": round(latest, 2) if latest is not None else None,
        "latest_price_date": prices[-1][0].isoformat() if prices else None,
        "holding": holding, "transactions": [_transaction_payload(r) for r in reversed(rows)],
        "market_data_error": None if prices else "No QQQ market-price data available",
    }]}


def build_history(instrument_id: str, range_key: str = "1y", repo: TransactionRepository | None = None) -> dict[str, Any]:
    if instrument_id != "qqq":
        raise ValueError("Unsupported US instrument")
    repo = repo or TransactionRepository()
    rows = repo.list_for(instrument_id)
    prices = fetch_price_history("QQQ")
    rk = range_key if range_key in RANGE_DAYS else "1y"
    days = RANGE_DAYS[rk]
    visible = prices
    if prices and days is not None:
        cutoff = prices[-1][0] - timedelta(days=days)
        visible = [point for point in prices if point[0] >= cutoff]
    average = calculate_holding(rows, prices[-1][1] if prices else None)["average_buy_price_usd"]
    first_date = visible[0][0] if visible else None
    purchases = [r for r in rows if first_date is None or r.purchased_at.date() >= first_date]
    latest = prices[-1][1] if prices else None
    comparison = round((latest / average - 1) * 100, 2) if latest is not None and average else None
    return {
        "instrument_id": instrument_id, "range": rk,
        "points": [{"date": d.isoformat(), "price": round(p, 4)} for d, p in visible],
        "purchases": [_transaction_payload(r) for r in purchases],
        "average_buy_price_usd": average, "latest_vs_average_pct": comparison,
        "error": None if prices else "No QQQ market-price data available",
    }


def add_buy(payload: dict[str, Any], repo: TransactionRepository | None = None) -> dict[str, Any]:
    transaction = BuyTransaction(id=str(uuid.uuid4()), **payload)
    return _transaction_payload((repo or TransactionRepository()).add(transaction))
