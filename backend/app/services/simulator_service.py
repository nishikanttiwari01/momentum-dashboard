from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import math

import pyarrow as pa

from app.core import config as app_config
from app.repos.parquet import datasets
from app.repos.parquet.scores_repo import ScoresRepo


def _to_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _date_range(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


def _row_price(row: Dict[str, object]) -> Optional[float]:
    for key in ("close", "last", "price"):
        val = row.get(key)
        if val is None:
            continue
        try:
            f = float(val)
            if f == f:  # filter NaN
                return f
        except Exception:
            continue
    return None


def _row_score(row: Dict[str, object]) -> Optional[float]:
    val = row.get("score")
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


def _as_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n"}:
        return False
    return None


def _is_recommended(row: Dict[str, object]) -> bool:
    rec_raw = row.get("recommendation")
    rec_val = _as_bool(rec_raw)
    if rec_val is True:
        return True
    if isinstance(rec_raw, str) and rec_raw.strip().lower() in {"yes", "y"}:
        return True
    for key in ("next_action_code", "next_action"):
        code = str(row.get(key) or "").strip().upper()
        if code in {"BUY_BREAKOUT", "BUY_PULLBACK", "BUY_STARTER"}:
            return True
    buy_flag = _as_bool(row.get("buy_flag"))
    return bool(buy_flag)


@dataclass
class SimulationParams:
    min_score: float
    min_adx: float
    atr_pct_min: float
    atr_pct_max: float
    prox52w_min_pct: float
    pivot_clear_min_pct: float
    pivot_clear_max_pct: float
    base_len_min_bars: int
    relvol20_min: float
    day_change_max_pct: float
    liquidity_min: float
    stop_loss_pct: float
    take_profit_pct: float
    round_trip_cost_pct: float = 0.0035
    max_hold_days: Optional[int] = None
    top_n: Optional[int] = None
    first_trade_only: bool = False
    recommendation_only: bool = True
    # R-ratio target: if set, target = entry + r_ratio_target × risk (overrides take_profit_pct).
    r_ratio_target: Optional[float] = None
    r_ratio_target_t2: Optional[float] = None
    # Partial exit at T1: fraction sold at T1 (rest trailed to breakeven).
    t1_partial_exit_pct: float = 50.0
    # Gap filter: skip entry if next-bar open is > this % above signal price.
    max_entry_gap_pct: float = 0.03
    # Risk-based position sizing: fraction of portfolio risked per trade.
    risk_pct_per_trade: float = 1.5
    # Hard cap on simultaneous open positions — matches selection_policy.max_open_positions.
    max_open_positions: int = 5


@dataclass
class TradeResult:
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    pnl_pct: float
    holding_days: int
    notes: Optional[str] = None


@dataclass
class SeriesPoint:
    date: str
    close: Optional[float]


@dataclass
class DailyBar:
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]


@dataclass
class SimulationRun:
    label: str
    params: SimulationParams
    trades: List[TradeResult]
    summary: Dict[str, float]
    charts: Dict[str, List[SeriesPoint]]


# ------------------------------------------------------------
# Honest performance statistics (pure-python, no numpy/pandas)
# ------------------------------------------------------------

_TRADING_DAYS_PER_YEAR = 252


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _downside_stddev(values: List[float], target: float = 0.0) -> float:
    downs = [min(0.0, v - target) for v in values]
    if not downs:
        return 0.0
    sq = [d * d for d in downs]
    var = sum(sq) / max(1, len(sq) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _sharpe_annualised(daily_returns: List[float], rf_daily: float = 0.0) -> float:
    """Annualised Sharpe from a list of daily decimal returns (0.01 = 1%)."""
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - rf_daily for r in daily_returns]
    sd = _stddev(excess)
    if sd <= 0:
        return 0.0
    return (_mean(excess) / sd) * math.sqrt(_TRADING_DAYS_PER_YEAR)


def _sortino_annualised(daily_returns: List[float], rf_daily: float = 0.0) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - rf_daily for r in daily_returns]
    dd = _downside_stddev(excess, 0.0)
    if dd <= 0:
        return 0.0
    return (_mean(excess) / dd) * math.sqrt(_TRADING_DAYS_PER_YEAR)


def _profit_factor(pnl_values: List[float]) -> float:
    wins = sum(p for p in pnl_values if p > 0)
    losses = -sum(p for p in pnl_values if p < 0)
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def _expectancy_per_trade(pnl_values: List[float]) -> float:
    if not pnl_values:
        return 0.0
    return sum(pnl_values) / len(pnl_values)


def _cagr_from_equity(equity_series: List[Tuple[date, float]]) -> float:
    """Compound annual growth rate from a dated equity curve.

    equity_series: list of (date, equity) pairs where equity starts at 1.0.
    """
    if len(equity_series) < 2:
        return 0.0
    start_dt, start_eq = equity_series[0]
    end_dt, end_eq = equity_series[-1]
    if start_eq <= 0:
        return 0.0
    days = max(1, (end_dt - start_dt).days)
    years = days / 365.25
    if years <= 0:
        return 0.0
    ratio = end_eq / start_eq
    if ratio <= 0:
        return -1.0
    try:
        return ratio ** (1.0 / years) - 1.0
    except Exception:
        return 0.0


def _monthly_returns_from_equity(
    equity_series: List[Tuple[date, float]],
) -> Dict[str, float]:
    """Compute month-over-month percent return from a dated equity curve.

    Returns a dict keyed by 'YYYY-MM' with decimal returns (0.01 = 1%).
    """
    if not equity_series:
        return {}
    month_end: Dict[str, float] = {}
    for d, eq in equity_series:
        key = f"{d.year:04d}-{d.month:02d}"
        # Last observation in the month wins.
        month_end[key] = eq
    months = sorted(month_end.keys())
    if not months:
        return {}
    # Prepend the opening equity (just before the first day) so the first
    # month's return is measured against the start.
    first_dt, first_eq = equity_series[0]
    prev_eq = first_eq
    out: Dict[str, float] = {}
    for m in months:
        eq = month_end[m]
        if prev_eq and prev_eq > 0:
            out[m] = (eq / prev_eq) - 1.0
        else:
            out[m] = 0.0
        prev_eq = eq
    return out


class SimulatorService:
    """
    Lightweight in-memory simulator that builds a pool history from daily scores parquet
    and applies simple exit rules (stop-loss + holding timeout). This intentionally mirrors
    the app's equal-weight assumption per trade.
    """

    def __init__(self) -> None:
        self.scores_repo = ScoresRepo()
        self._scores_cache: Dict[str, pa.Table] = {}
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._bar_cache: Dict[str, Dict[str, DailyBar]] = {}

    @staticmethod
    def default_params() -> SimulationParams:
        cfg = app_config.load()
        # profiles.buy is a Dict[str, StrategyBuyProfileConfig]; use .get() not getattr.
        buy_profiles = cfg.strategy.profiles.buy or {}
        swing = buy_profiles.get("swing_eod")
        sell_common = getattr(cfg.strategy.profiles.sell, "common", None)
        stop_cfg = getattr(sell_common, "stop", None)
        targets_cfg = getattr(sell_common, "targets", None)
        atr_range = getattr(swing, "atr_pct", None)
        if atr_range is None:
            atr_range_tuple = (0.0, 8.0)
        elif hasattr(atr_range, "min"):
            atr_range_tuple = (atr_range.min or 0.0, atr_range.max or 8.0)
        elif isinstance(atr_range, (list, tuple)):
            atr_range_tuple = (float(atr_range[0]), float(atr_range[1]))
        else:
            atr_range_tuple = (0.0, 8.0)
        pivot_range = getattr(swing, "pivot_clear_pct", None)
        if pivot_range is None:
            pivot_range_tuple = (-2.0, 5.0)
        elif hasattr(pivot_range, "min"):
            pivot_range_tuple = (pivot_range.min if pivot_range.min is not None else -2.0,
                                 pivot_range.max if pivot_range.max is not None else 5.0)
        elif isinstance(pivot_range, (list, tuple)):
            pivot_range_tuple = (float(pivot_range[0]), float(pivot_range[1]))
        else:
            pivot_range_tuple = (-2.0, 5.0)
        return SimulationParams(
            min_score=float(getattr(swing, "min_score", 65)),
            min_adx=float(getattr(swing, "adx14_min", 22)),
            atr_pct_min=atr_range_tuple[0],
            atr_pct_max=atr_range_tuple[1],
            prox52w_min_pct=float(getattr(swing, "prox52w_min_pct", -8)),
            pivot_clear_min_pct=pivot_range_tuple[0],
            pivot_clear_max_pct=pivot_range_tuple[1],
            base_len_min_bars=int(getattr(swing, "base_len_min_bars", 5)),
            relvol20_min=float(getattr(swing, "relvol20_min", 1.2)),
            day_change_max_pct=float(getattr(swing, "day_change_max_pct", 6.0)),
            liquidity_min=float(getattr(swing, "liquidity_min_traded_value_20d", 50_000_000)),
            stop_loss_pct=float(getattr(stop_cfg, "atr_multiple", 2.0) or 2.0) * 0.03,  # approx 6% for ATR=3%
            take_profit_pct=float(getattr(targets_cfg, "t1_gain_pct", 10) or 10) / 100.0,
            round_trip_cost_pct=0.0035,
            max_hold_days=getattr(getattr(sell_common, "timeout", None), "max_holding_days", None),
            r_ratio_target=float(getattr(targets_cfg, "r_ratio_target", None) or 2.0) or None,
            r_ratio_target_t2=float(getattr(targets_cfg, "r_ratio_target_t2", None) or 3.0) or None,
            t1_partial_exit_pct=float(getattr(targets_cfg, "t1_partial_exit_pct", 50.0) or 50.0),
            max_entry_gap_pct=0.03,
            risk_pct_per_trade=float(getattr(cfg.selection_policy, "risk_pct_per_trade", 1.5) or 1.5),
            max_open_positions=int(getattr(cfg.selection_policy, "max_open_positions", 5) or 5),
        )

    @staticmethod
    def _apply_overrides(base: SimulationParams, overrides: Dict[str, object]) -> SimulationParams:
        data = asdict(base)
        for key, val in overrides.items():
            if key in data:
                data[key] = val
        return SimulationParams(**data)

    @staticmethod
    def _split_walk_forward_windows(
        start: date,
        end: date,
        splits: int,
    ) -> List[Tuple[str, date, date]]:
        """Divide [start, end] into `splits` contiguous, non-overlapping windows.

        Returns list of (label, segment_start, segment_end). Used for honest
        walk-forward reporting instead of in-sample grid-search overfitting.
        """
        if splits <= 1:
            return [("walk_1_of_1", start, end)]
        total_days = (end - start).days
        if total_days <= 0:
            return [("walk_1_of_1", start, end)]
        splits = max(2, int(splits))
        chunk = max(1, total_days // splits)
        out: List[Tuple[str, date, date]] = []
        cursor = start
        for i in range(splits):
            if i == splits - 1:
                seg_end = end
            else:
                seg_end = min(end, cursor + timedelta(days=chunk - 1))
            if seg_end < cursor:
                seg_end = cursor
            out.append((f"walk_{i+1}_of_{splits}", cursor, seg_end))
            cursor = seg_end + timedelta(days=1)
            if cursor > end:
                break
        return out

    def _load_scores_for_asof(self, as_of: str) -> pa.Table:
        if as_of in self._scores_cache:
            return self._scores_cache[as_of]
        tab = datasets.scan_scores_daily(as_of)
        self._scores_cache[as_of] = tab
        return tab

    def _candidate_rows_for_day(self, day: date, params: SimulationParams) -> List[Dict[str, object]]:
        tab = self._load_scores_for_asof(day.isoformat())
        if tab.num_rows == 0:
            return []
        cols_needed = {c for c in (
            "symbol",
            "score",
            "adx",
            "adx14",
            "atr_pct",
            "buy_flag",
            "recommendation",
            "next_action",
            "next_action_code",
            "open",
            "high",
            "low",
            "close",
            "last",
            "price",
            "proximity_52w_high_pct",
            "pct_from_52w_high",
            "pivot_clear_pct",
            "base_len_bars",
            "relvol20",
            "day_change_pct",
            "change_pct",
            "liquidity",
            "median_traded_value_20d",
        ) if c in tab.column_names}
        tab = tab.select(list(cols_needed))
        rows = tab.to_pylist()

        filtered: List[Dict[str, object]] = []
        for row in rows:
            score = _row_score(row)
            adx = None
            for key in ("adx14", "adx"):
                if key in row and row[key] is not None:
                    try:
                        adx = float(row[key])
                    except Exception:
                        pass
                    break
            atr_pct = None
            if "atr_pct" in row and row["atr_pct"] is not None:
                try:
                    atr_pct = float(row["atr_pct"])
                except Exception:
                    pass
            prox52 = None
            for key in ("proximity_52w_high_pct", "pct_from_52w_high"):
                if key in row and row[key] is not None:
                    try:
                        prox52 = float(row[key])
                    except Exception:
                        pass
                    break
            pivot_clear = None
            if "pivot_clear_pct" in row and row["pivot_clear_pct"] is not None:
                try:
                    pivot_clear = float(row["pivot_clear_pct"])
                except Exception:
                    pass
            base_len = None
            if "base_len_bars" in row and row["base_len_bars"] is not None:
                try:
                    base_len = float(row["base_len_bars"])
                except Exception:
                    pass
            relvol20 = None
            if "relvol20" in row and row["relvol20"] is not None:
                try:
                    relvol20 = float(row["relvol20"])
                except Exception:
                    pass
            day_chg = None
            for key in ("day_change_pct", "change_pct"):
                if key in row and row[key] is not None:
                    try:
                        day_chg = float(row[key])
                    except Exception:
                        pass
                    break
            liquidity = None
            for key in ("liquidity", "median_traded_value_20d"):
                if key in row and row[key] is not None:
                    try:
                        liquidity = float(row[key])
                    except Exception:
                        pass
                    break

            if score is None or score < params.min_score:
                continue
            if adx is None or adx < params.min_adx:
                continue
            if atr_pct is None or atr_pct < params.atr_pct_min or atr_pct > params.atr_pct_max:
                continue
            if prox52 is None or prox52 < params.prox52w_min_pct:
                continue
            if pivot_clear is None or pivot_clear < params.pivot_clear_min_pct or pivot_clear > params.pivot_clear_max_pct:
                continue
            if base_len is None or base_len < params.base_len_min_bars:
                continue
            if relvol20 is None or relvol20 < params.relvol20_min:
                continue
            if day_chg is None or day_chg > params.day_change_max_pct:
                continue
            if liquidity is None or liquidity < params.liquidity_min:
                continue
            if params.recommendation_only:
                # Live-signal mode: only enter when the live system flagged a buy.
                # Depends on buy_flag / action codes stored in the parquet snapshot.
                if not _is_recommended(row):
                    continue
            # recommendation_only=False → pure quantitative backtest: all quantitative
            # filters above already pass; no stored buy_flag required. This lets us
            # evaluate NEW screening criteria against historical data even when the
            # parquet snapshots were collected with an older set of rules.
            price = _row_price(row)
            if price is None:
                continue
            filtered.append({
                **row,
                "price": price,
                "score": score,
                "adx": adx,
                "atr_pct": atr_pct,
                "prox52": prox52,
                "pivot_clear_pct": pivot_clear,
                "base_len_bars": base_len,
                "relvol20": relvol20,
                "day_change_pct": day_chg,
                "liquidity": liquidity,
            })

        filtered.sort(key=lambda r: r.get("score") or 0, reverse=True)
        if params.top_n:
            return filtered[: params.top_n]
        return filtered

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            num = float(value)
        except Exception:
            return None
        if num != num:
            return None
        return num

    @classmethod
    def _bar_from_row(cls, row: Dict[str, object]) -> DailyBar:
        open_price = cls._safe_float(row.get("open"))
        high_price = cls._safe_float(row.get("high"))
        low_price = cls._safe_float(row.get("low"))
        close_price = cls._safe_float(row.get("close") or row.get("last") or row.get("price"))
        if high_price is None and close_price is not None:
            high_price = close_price
        if low_price is None and close_price is not None:
            low_price = close_price
        if open_price is None and close_price is not None:
            open_price = close_price
        return DailyBar(
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
        )

    def _bar_map_for_day(self, day: date, symbols: Optional[Iterable[str]] = None) -> Dict[str, DailyBar]:
        target_syms = {s.upper() for s in symbols} if symbols else None
        day_key = day.isoformat()
        if day_key in self._bar_cache:
            if target_syms:
                return {k: v for k, v in self._bar_cache[day_key].items() if k in target_syms}
            return dict(self._bar_cache[day_key])

        tab = self._load_scores_for_asof(day_key)
        if tab.num_rows == 0 or "symbol" not in tab.column_names:
            self._bar_cache[day_key] = {}
            return {}

        wanted = [c for c in ("symbol", "open", "high", "low", "close", "last", "price") if c in tab.column_names]
        if set(wanted) != set(tab.column_names):
            tab = tab.select(wanted)

        bar_map: Dict[str, DailyBar] = {}
        for row in tab.to_pylist():
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            if target_syms is not None and symbol not in target_syms:
                continue
            bar_map[symbol] = self._bar_from_row(row)
        self._bar_cache[day_key] = bar_map
        return dict(bar_map)

    def _price_map_for_day(self, day: date, symbols: Optional[Iterable[str]] = None) -> Dict[str, Optional[float]]:
        bars = self._bar_map_for_day(day, symbols)
        return {symbol: bar.close for symbol, bar in bars.items()}

    def _build_price_cache_from_prices(self, start: date, end: date) -> None:
        """
        Preload daily close prices from the prices parquet table for the simulation window.
        This gives more reliable pricing than relying only on scores snapshots.
        """
        tab = datasets.scan("prices", run_id=None, dt_range=(start.isoformat(), end.isoformat()), columns=["symbol", "close", "dt"])
        if tab.num_rows == 0 or not {"symbol", "close", "dt"}.issubset(set(tab.column_names)):
            return
        col_sym = tab.column("symbol")
        col_close = tab.column("close")
        col_dt = tab.column("dt")
        for i in range(tab.num_rows):
            try:
                sym = str(col_sym[i].as_py()).upper()
                dt_val = col_dt[i].as_py()
                day_key = dt_val.isoformat() if hasattr(dt_val, "isoformat") else str(dt_val)
                close_val = col_close[i].as_py()
                if close_val is None:
                    continue
                price = float(close_val)
            except Exception:
                continue
            self._price_cache.setdefault(day_key, {})[sym] = price

    def _series_from_cache(self, symbols: Iterable[str], start: date, end: date) -> Dict[str, List[SeriesPoint]]:
        series: Dict[str, List[SeriesPoint]] = {s: [] for s in symbols}
        for day in _date_range(start, end):
            day_key = day.isoformat()
            price_map = self._price_cache.get(day_key, {})
            for sym in series:
                price = price_map.get(sym)
                series[sym].append(SeriesPoint(date=day_key, close=price if price is not None else None))
        return series

    def _build_price_series(self, symbols: Iterable[str], start: date, end: date) -> Dict[str, List[SeriesPoint]]:
        series: Dict[str, List[SeriesPoint]] = {sym: [] for sym in symbols}
        for day in _date_range(start, end):
            as_of = datasets.latest_daily_at_or_before(day.isoformat())
            if not as_of:
                continue
            tab = self._load_scores_for_asof(as_of)
            if tab.num_rows == 0 or "symbol" not in tab.column_names:
                continue
            map_rows: Dict[str, float] = {}
            col_sym = tab.column("symbol")
            col_close = tab.column("close") if "close" in tab.column_names else None
            col_last = tab.column("last") if "last" in tab.column_names else None
            for i in range(tab.num_rows):
                sym = col_sym[i].as_py()
                if sym not in series:
                    continue
                price_val = None
                if col_close is not None:
                    price_val = col_close[i].as_py()
                if price_val is None and col_last is not None:
                    price_val = col_last[i].as_py()
                try:
                    price = float(price_val) if price_val is not None else None
                except Exception:
                    price = None
                map_rows[sym] = price
            for sym in series:
                if sym in map_rows:
                    series[sym].append(SeriesPoint(date=day.isoformat(), close=map_rows[sym]))
        return series

    def simulate(self, start: date, end: date, params: SimulationParams, manual_symbols: Optional[List[str]] = None, label: str = "baseline") -> SimulationRun:
        start_date = _to_date(start)
        end_date = _to_date(end)
        manual_syms = {s.upper() for s in (manual_symbols or []) if s}

        # preload prices for the window to avoid repeated parquet scans
        self._price_cache = {}
        self._bar_cache = {}
        self._build_price_cache_from_prices(start_date, end_date)

        open_positions: Dict[str, Dict[str, object]] = {}
        pending_entries: Dict[str, Dict[str, object]] = {}
        closed: List[TradeResult] = []
        seen_symbols: set[str] = set()
        open_position_counts: List[int] = []

        # Track a daily mark-to-market equity curve so we can compute Sharpe,
        # Sortino, max drawdown and monthly returns honestly (not from a
        # trade-count sequence of compounded pnl).
        # Equal-weight assumption: each position represents 1 / max_open_positions
        # fraction of the book. Enforced hard cap in the entry loop below.
        slots = int(params.max_open_positions) if params.max_open_positions and params.max_open_positions > 0 else 5
        slots = max(1, slots)
        realised_pnl_decimal = 0.0  # accumulated closed-trade returns, already equal-weighted
        equity_series: List[Tuple[date, float]] = []

        def _entry_price(bar: DailyBar) -> Optional[float]:
            return bar.open or bar.close

        def _close_price(bar: DailyBar) -> Optional[float]:
            return bar.close or bar.open

        def _trade(
            *,
            symbol: str,
            entry_date: date,
            exit_date: date,
            entry_price: float,
            exit_price: float,
            note: str,
        ) -> TradeResult:
            gross_return = ((exit_price - entry_price) / entry_price) if entry_price else 0.0
            net_return = gross_return - float(params.round_trip_cost_pct or 0.0)
            return TradeResult(
                symbol=symbol,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=round(float(entry_price), 6),
                exit_price=round(float(exit_price), 6),
                pnl_pct=round(float(net_return * 100.0), 6),
                holding_days=(exit_date - entry_date).days,
                notes=note,
            )

        for day in _date_range(start_date, end_date):
            candidates = self._candidate_rows_for_day(day, params)
            candidate_syms = {str(r.get("symbol") or "").upper() for r in candidates if r.get("symbol")}
            bar_syms = candidate_syms | set(open_positions.keys()) | set(pending_entries.keys()) | set(manual_syms)
            daily_bars = self._bar_map_for_day(day, bar_syms) if bar_syms else {}

            # Signals become entries on the next available bar, not the signal bar.
            for sym in list(pending_entries.keys()):
                if params.first_trade_only and sym in seen_symbols:
                    pending_entries.pop(sym, None)
                    continue
                if sym in open_positions:
                    pending_entries.pop(sym, None)
                    continue
                # Enforce hard position cap so equity model stays valid.
                if len(open_positions) >= slots:
                    break
                bar = daily_bars.get(sym)
                if bar is None:
                    continue
                entry_price = _entry_price(bar)
                last_price = _close_price(bar)
                if entry_price is None:
                    continue
                # Gap filter: skip entries where next-bar open has already gapped
                # too far above the signal price. Buying into a 4%+ gap means
                # the easy money is gone and the R:R is severely compressed.
                signal_price = pending_entries[sym].get("signal_price")
                if (
                    params.max_entry_gap_pct is not None
                    and params.max_entry_gap_pct > 0
                    and signal_price is not None
                    and signal_price > 0
                    and entry_price > signal_price * (1 + params.max_entry_gap_pct)
                ):
                    pending_entries.pop(sym, None)
                    continue
                # Compute stop and R-ratio target from the actual entry price.
                atr_pct = self._safe_float(pending_entries[sym].get("atr_pct"))
                stop_for_pos: Optional[float] = None
                target_for_pos: Optional[float] = None
                if atr_pct is not None and atr_pct > 0 and entry_price > 0:
                    atr_val = entry_price * (atr_pct / 100.0) * 2.0  # ATR × 2.0 multiple
                    stop_for_pos = entry_price - atr_val
                    if stop_for_pos > 0 and params.r_ratio_target is not None:
                        risk = entry_price - stop_for_pos
                        target_for_pos = entry_price + risk * params.r_ratio_target
                open_positions[sym] = {
                    "entry_date": day,
                    "entry_price": entry_price,
                    "last_price": last_price or entry_price,
                    "signal_date": pending_entries[sym].get("signal_date"),
                    "atr_stop": stop_for_pos,
                    "r_target": target_for_pos,
                    "t1_hit": False,
                    "stop_at_entry": False,
                }
                seen_symbols.add(sym)
                pending_entries.pop(sym, None)

            # Manual symbols enter on the first trading day with data.
            for sym in list(manual_syms):
                if params.first_trade_only and sym in seen_symbols:
                    manual_syms.remove(sym)
                    continue
                if sym in open_positions:
                    manual_syms.remove(sym)
                    continue
                bar = daily_bars.get(sym)
                if bar is None:
                    continue
                entry_price = _entry_price(bar)
                last_price = _close_price(bar)
                if entry_price is None:
                    continue
                open_positions[sym] = {
                    "entry_date": day,
                    "entry_price": entry_price,
                    "last_price": last_price or entry_price,
                    "signal_date": start_date,
                }
                seen_symbols.add(sym)
                manual_syms.remove(sym)

            open_position_counts.append(len(open_positions))

            to_exit: List[Tuple[str, TradeResult]] = []
            for sym, pos in open_positions.items():
                bar = daily_bars.get(sym)
                if bar is None:
                    continue
                close_price = _close_price(bar)
                if close_price is not None:
                    pos["last_price"] = close_price
                entry_price = float(pos.get("entry_price") or 0.0)
                entry_date = pos["entry_date"]
                holding_days = (day - entry_date).days

                # Use per-position R-ratio stop/target if available (computed at entry);
                # fall back to fixed-pct params for legacy / manual symbols.
                atr_stop = self._safe_float(pos.get("atr_stop"))
                r_target = self._safe_float(pos.get("r_target"))
                stop_at_entry = bool(pos.get("stop_at_entry"))  # set after T1 partial exit

                if atr_stop is not None and atr_stop > 0:
                    # After T1 partial, stop is raised to entry (risk-free remainder).
                    stop_price = entry_price if stop_at_entry else atr_stop
                elif params.stop_loss_pct:
                    stop_price = entry_price * (1 - params.stop_loss_pct)
                else:
                    stop_price = None

                if r_target is not None and r_target > 0:
                    target_price = r_target
                elif params.take_profit_pct:
                    target_price = entry_price * (1 + params.take_profit_pct)
                else:
                    target_price = None

                # T2 target for the remainder after partial T1
                t2_target: Optional[float] = None
                if params.r_ratio_target_t2 is not None and atr_stop is not None and atr_stop > 0:
                    risk = entry_price - atr_stop
                    t2_target = entry_price + risk * params.r_ratio_target_t2

                open_price = bar.open if bar.open is not None else close_price
                known_prices = [v for v in (open_price, close_price) if v is not None]
                high_price = bar.high if bar.high is not None else (max(known_prices) if known_prices else None)
                low_price = bar.low if bar.low is not None else (min(known_prices) if known_prices else None)

                exit_price: Optional[float] = None
                exit_reason: Optional[str] = None
                t1_already_hit = bool(pos.get("t1_hit"))

                if stop_price is not None and open_price is not None and open_price <= stop_price:
                    exit_price = open_price
                    exit_reason = "gap_stop"
                elif t2_target is not None and open_price is not None and open_price >= t2_target and t1_already_hit:
                    exit_price = open_price
                    exit_reason = "gap_t2"
                elif target_price is not None and open_price is not None and open_price >= target_price and not t1_already_hit:
                    exit_price = open_price
                    exit_reason = "gap_t1_partial"
                elif stop_price is not None and low_price is not None and low_price <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif t2_target is not None and high_price is not None and high_price >= t2_target and t1_already_hit:
                    exit_price = t2_target
                    exit_reason = "target_t2"
                elif target_price is not None and high_price is not None and high_price >= target_price and not t1_already_hit:
                    # Partial T1 exit: book 50% profit, trail rest to breakeven.
                    # In simulation we approximate this as a single blended outcome:
                    # 50% exits at T1 price, 50% is trailed with stop moved to entry.
                    pos["t1_hit"] = True
                    pos["stop_at_entry"] = True  # tighten stop to entry for remainder
                    exit_price = None             # don't close yet; trail the rest
                    exit_reason = None
                elif params.max_hold_days is not None and holding_days >= int(params.max_hold_days):
                    exit_price = close_price
                    exit_reason = "timeout"

                if exit_price is not None and exit_reason is not None:
                    partial = exit_reason in ("gap_t1_partial",)
                    to_exit.append(
                        (
                            sym,
                            _trade(
                                symbol=sym,
                                entry_date=entry_date,
                                exit_date=day,
                                entry_price=entry_price,
                                exit_price=exit_price,
                                note=exit_reason,
                            ),
                            partial,
                        )
                    )
            for sym, trade, is_partial in to_exit:
                closed.append(trade)
                partial_fraction = (params.t1_partial_exit_pct / 100.0) if is_partial else 1.0
                # Contribution to equity = pnl × fraction-of-position / slots.
                realised_pnl_decimal += (trade.pnl_pct / 100.0) * partial_fraction / slots
                if is_partial:
                    # Keep position open for remainder — T1 arms breakeven stop.
                    pos = open_positions.get(sym)
                    if pos is not None:
                        pos["t1_hit"] = True
                        pos["stop_at_entry"] = True
                else:
                    open_positions.pop(sym, None)

            # End-of-day mark-to-market: realised pnl + open-position MTM vs entry.
            open_mtm_decimal = 0.0
            for pos in open_positions.values():
                last_price = pos.get("last_price")
                entry_price = pos.get("entry_price")
                if not last_price or not entry_price:
                    continue
                try:
                    pos_return = (float(last_price) - float(entry_price)) / float(entry_price)
                except Exception:
                    pos_return = 0.0
                open_mtm_decimal += pos_return / slots
            equity_today = 1.0 + realised_pnl_decimal + open_mtm_decimal
            equity_series.append((day, equity_today))

            for row in candidates:
                sym = str(row.get("symbol") or "").upper()
                if not sym:
                    continue
                if params.first_trade_only and sym in seen_symbols:
                    continue
                if sym in open_positions or sym in pending_entries:
                    continue
                if row.get("price") is None:
                    continue
                pending_entries[sym] = {
                    "signal_date": day,
                    "signal_price": row["price"],
                    "atr_pct": row.get("atr_pct"),
                }

        for sym, pos in list(open_positions.items()):
            last_price = pos.get("last_price")
            if last_price is None:
                continue
            closed.append(
                _trade(
                    symbol=sym,
                    entry_date=pos["entry_date"],
                    exit_date=end_date,
                    entry_price=float(pos.get("entry_price") or last_price),
                    exit_price=float(last_price),
                    note="window_close",
                )
            )

        symbols_for_chart = {t.symbol for t in closed}
        chart_start = start_date - timedelta(days=30)
        chart_end = end_date + timedelta(days=30)
        # extend cache range so charts have prices pre/post window
        self._build_price_cache_from_prices(chart_start, chart_end)
        charts = self._series_from_cache(symbols_for_chart, chart_start, chart_end)

        closed.sort(key=lambda trade: (trade.exit_date, trade.symbol))
        pnl_values = [t.pnl_pct for t in closed]
        avg_return = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0
        win_rate = sum(1 for p in pnl_values if p > 0) / len(pnl_values) * 100 if pnl_values else 0.0
        avg_holding_days = sum(t.holding_days for t in closed) / len(closed) if closed else 0.0

        # Ensure a final equity point at end_date so we capture any trades or
        # window-close exits that happened after the last iterated day.
        if not equity_series or equity_series[-1][0] < end_date:
            final_equity = 1.0 + realised_pnl_decimal
            equity_series.append((end_date, final_equity))
        # Recompute drawdown from the equity curve, which is the honest measure.
        peak = 0.0
        max_drawdown = 0.0
        for _, eq in equity_series:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (eq / peak) - 1.0
                if dd < max_drawdown / 100.0:
                    max_drawdown = dd * 100.0
        total_return = (equity_series[-1][1] - 1.0) * 100.0 if equity_series else 0.0

        # Daily returns from the equity curve for Sharpe / Sortino.
        daily_returns: List[float] = []
        prev_eq = equity_series[0][1] if equity_series else 1.0
        for _, eq in equity_series[1:]:
            if prev_eq > 0:
                daily_returns.append((eq / prev_eq) - 1.0)
            prev_eq = eq
        sharpe = _sharpe_annualised(daily_returns)
        sortino = _sortino_annualised(daily_returns)

        # Per-trade statistics.
        wins = [p for p in pnl_values if p > 0]
        losses = [p for p in pnl_values if p < 0]
        avg_win_pct = _mean(wins) if wins else 0.0
        avg_loss_pct = _mean(losses) if losses else 0.0
        profit_factor = _profit_factor(pnl_values)
        expectancy = _expectancy_per_trade(pnl_values)
        cagr = _cagr_from_equity(equity_series) * 100.0
        monthly_returns_decimal = _monthly_returns_from_equity(equity_series)
        monthly_returns_pct = {k: v * 100.0 for k, v in monthly_returns_decimal.items()}
        monthly_values = list(monthly_returns_decimal.values())
        monthly_mean_pct = _mean(monthly_values) * 100.0 if monthly_values else 0.0
        monthly_stddev_pct = _stddev(monthly_values) * 100.0 if monthly_values else 0.0
        positive_months = sum(1 for v in monthly_values if v > 0)
        negative_months = sum(1 for v in monthly_values if v < 0)

        # Expose the equity curve under charts so the UI (or caller) can plot it
        # alongside the per-symbol price charts.
        charts["_equity_curve"] = [
            SeriesPoint(date=d.isoformat(), close=float(eq)) for d, eq in equity_series
        ]

        summary = {
            "trades": float(len(closed)),
            "avg_return_pct": float(avg_return),
            "avg_win_pct": float(avg_win_pct),
            "avg_loss_pct": float(avg_loss_pct),
            "win_rate_pct": float(win_rate),
            "profit_factor": float(profit_factor) if profit_factor != float("inf") else -1.0,
            "expectancy_per_trade_pct": float(expectancy),
            "total_return_pct": float(total_return),
            "cagr_pct": float(cagr),
            "sharpe_annualised": float(sharpe),
            "sortino_annualised": float(sortino),
            "avg_holding_days": float(avg_holding_days),
            "max_drawdown_pct": float(max_drawdown),
            "avg_open_positions": float(sum(open_position_counts) / len(open_position_counts)) if open_position_counts else 0.0,
            "max_open_positions": float(max(open_position_counts)) if open_position_counts else 0.0,
            "assumed_round_trip_cost_pct": float((params.round_trip_cost_pct or 0.0) * 100.0),
            "slots_assumed": float(slots),
            "entry_model": "next_bar_open",
            "exit_model": "daily_bar_range",
            "monthly_return_pct_by_month": monthly_returns_pct,
            "monthly_return_mean_pct": float(monthly_mean_pct),
            "monthly_return_stddev_pct": float(monthly_stddev_pct),
            "positive_months": float(positive_months),
            "negative_months": float(negative_months),
        }

        return SimulationRun(
            label=label,
            params=params,
            trades=closed,
            summary=summary,
            charts=charts,
        )

    def run_with_variants(
        self,
        start: date,
        end: date,
        base_params: SimulationParams,
        variants: Optional[List[Tuple[str, SimulationParams]]] = None,
        sweep: Optional[Dict[str, object]] = None,
        manual_symbols: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> Tuple[List[SimulationRun], Dict[str, object]]:
        """Run a baseline simulation, any explicit variants, and — if
        ``sweep.enabled`` is true — walk-forward segments of the window.

        Behaviour changed from prior versions:
          * The parameter grid-search has been REMOVED. Searching until a
            target return is hit is overfitting; it produced beautiful
            in-sample numbers that never held up live. The ``sweep.ranges``,
            ``sweep.target_total_return_pct`` and ``sweep.prefer_profitable``
            inputs are accepted for API back-compat but IGNORED.
          * ``sweep.enabled`` now controls walk-forward splitting. When true,
            the window is divided into N contiguous non-overlapping segments
            (default 4, or ``sweep.walk_forward_splits`` / ``sweep.max_runs``)
            and the SAME base_params is replayed on each segment. This gives
            honest out-of-sample stability checks.
          * Runs are returned in natural order (baseline, variants, walk
            segments) — no profitability-based reordering.
        """
        start_date = _to_date(start)
        end_date = _to_date(end)

        runs: List[SimulationRun] = [
            self.simulate(start_date, end_date, base_params, manual_symbols, label="baseline")
        ]

        sweep_cfg: Dict[str, object] = sweep if isinstance(sweep, dict) else {}
        walk_forward_enabled = bool(sweep_cfg.get("enabled"))
        # Accept either an explicit splits key or reuse `max_runs` as the
        # segment count (old field, new meaning). Cap to a sane range.
        raw_splits = (
            sweep_cfg.get("walk_forward_splits")
            or sweep_cfg.get("max_runs")
            or 4
        )
        try:
            walk_splits = max(1, min(int(raw_splits), 12))
        except Exception:
            walk_splits = 4

        ignored_keys: List[str] = []
        for key in ("ranges", "target_total_return_pct", "prefer_profitable", "min_runs", "seed"):
            if key in sweep_cfg:
                ignored_keys.append(key)

        walk_segments: List[Tuple[str, date, date]] = []
        if walk_forward_enabled:
            walk_segments = self._split_walk_forward_windows(start_date, end_date, walk_splits)

        total_planned = 1 + len(variants or []) + len(walk_segments)
        completed = len(runs)
        if progress_cb:
            progress_cb(completed, total_planned, "baseline")

        # Run explicit variants on the full window.
        for label, variant in (variants or []):
            runs.append(self.simulate(start_date, end_date, variant, manual_symbols, label=label))
            completed += 1
            if progress_cb:
                progress_cb(completed, total_planned, label)

        # Run walk-forward segments (same params as baseline; honest OOS check).
        for seg_label, seg_start, seg_end in walk_segments:
            runs.append(self.simulate(seg_start, seg_end, base_params, manual_symbols, label=seg_label))
            completed += 1
            if progress_cb:
                progress_cb(completed, total_planned, seg_label)

        # Compute stability summary across walk-forward segments, if any.
        walk_runs = [r for r in runs if r.label.startswith("walk_")]
        walk_stats: Dict[str, float] = {}
        if walk_runs:
            returns = [r.summary.get("total_return_pct", 0.0) for r in walk_runs]
            walk_stats = {
                "segments": float(len(walk_runs)),
                "mean_total_return_pct": float(_mean(returns)),
                "stddev_total_return_pct": float(_stddev(returns)),
                "min_total_return_pct": float(min(returns)) if returns else 0.0,
                "max_total_return_pct": float(max(returns)) if returns else 0.0,
                "positive_segments": float(sum(1 for r in returns if r > 0)),
            }

        meta: Dict[str, object] = {
            "runs_evaluated": len(runs),
            "planned_total_runs": int(total_planned),
            "walk_forward_enabled": bool(walk_forward_enabled),
            "walk_forward_splits": int(len(walk_segments)),
            "walk_forward_stats": walk_stats,
            "grid_search": "disabled",
            "ignored_sweep_keys": ignored_keys,
            "notice": (
                "Parameter grid-search removed to avoid overfitting. "
                "Set sweep.enabled=true to run walk-forward segments instead."
            ),
        }

        return runs, meta
