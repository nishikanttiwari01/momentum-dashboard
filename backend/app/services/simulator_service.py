from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

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
    max_hold_days: Optional[int] = None
    top_n: Optional[int] = None
    first_trade_only: bool = False


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
class SimulationRun:
    label: str
    params: SimulationParams
    trades: List[TradeResult]
    summary: Dict[str, float]
    charts: Dict[str, List[SeriesPoint]]


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

    @staticmethod
    def default_params() -> SimulationParams:
        cfg = app_config.load()
        swing = getattr(getattr(cfg.strategy.profiles, "buy", None), "swing_eod", None)
        sell_common = getattr(getattr(cfg.strategy.profiles, "sell", None), "common", None)
        stop_cfg = getattr(sell_common, "stop", None)
        atr_range = getattr(swing, "atr_pct", [0.0, 8.0]) or [0.0, 8.0]
        pivot_range = getattr(swing, "pivot_clear_pct", [-0.3, 6.0]) or [-0.3, 6.0]
        return SimulationParams(
            min_score=float(getattr(swing, "min_score", 70)),
            min_adx=float(getattr(swing, "adx14_min", 22)),
            atr_pct_min=float(atr_range[0] if isinstance(atr_range, (list, tuple)) else 0.0),
            atr_pct_max=float(atr_range[1] if isinstance(atr_range, (list, tuple)) else float(atr_range)),
            prox52w_min_pct=float(getattr(swing, "prox52w_min_pct", -8)),
            pivot_clear_min_pct=float(pivot_range[0] if isinstance(pivot_range, (list, tuple)) else -0.3),
            pivot_clear_max_pct=float(pivot_range[1] if isinstance(pivot_range, (list, tuple)) else 6.0),
            base_len_min_bars=int(getattr(swing, "base_len_min_bars", 5)),
            relvol20_min=float(getattr(swing, "relvol20_min", 1.3)),
            day_change_max_pct=float(getattr(swing, "day_change_max_pct", 6.0)),
            liquidity_min=float(getattr(swing, "liquidity_min_traded_value_20d", 50_000_000)),
            stop_loss_pct=float(getattr(stop_cfg, "floor_pct", 5) or 5) / 100.0,
            max_hold_days=getattr(getattr(sell_common, "timeout", None), "max_holding_days", None),
        )

    def _load_scores_for_asof(self, as_of: str) -> pa.Table:
        if as_of in self._scores_cache:
            return self._scores_cache[as_of]
        tab = datasets.scan_scores_daily(as_of)
        self._scores_cache[as_of] = tab
        return tab

    def _candidate_rows_for_day(self, day: date, params: SimulationParams) -> List[Dict[str, object]]:
        as_of = datasets.latest_daily_at_or_before(day.isoformat())
        if not as_of:
            return []
        tab = self._load_scores_for_asof(as_of)
        if tab.num_rows == 0:
            return []
        cols_needed = {c for c in (
            "symbol",
            "score",
            "adx",
            "adx14",
            "atr_pct",
            "buy_flag",
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
            if not bool(row.get("buy_flag", False)):
                continue
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

    def _price_map_for_day(self, day: date, symbols: Optional[Iterable[str]] = None) -> Dict[str, Optional[float]]:
        target_syms = {s.upper() for s in symbols} if symbols else None
        day_key = day.isoformat()
        if day_key in self._price_cache:
            if target_syms:
                return {k: v for k, v in self._price_cache[day_key].items() if k in target_syms}
            return dict(self._price_cache[day_key])
        as_of = datasets.latest_daily_at_or_before(day.isoformat())
        if not as_of:
            return {}
        tab = self._load_scores_for_asof(as_of)
        if tab.num_rows == 0 or "symbol" not in tab.column_names:
            return {}
        col_sym = tab.column("symbol")
        col_close = tab.column("close") if "close" in tab.column_names else None
        col_last = tab.column("last") if "last" in tab.column_names else None
        col_price = tab.column("price") if "price" in tab.column_names else None
        price_map: Dict[str, Optional[float]] = {}
        for i in range(tab.num_rows):
            sym = str(col_sym[i].as_py()).upper()
            if target_syms is not None and sym not in target_syms:
                continue
            price_val = None
            if col_close is not None:
                price_val = col_close[i].as_py()
            if price_val is None and col_last is not None:
                price_val = col_last[i].as_py()
            if price_val is None and col_price is not None:
                price_val = col_price[i].as_py()
            try:
                price_map[sym] = float(price_val) if price_val is not None else None
            except Exception:
                price_map[sym] = None
        self._price_cache[day_key] = {k: v for k, v in price_map.items() if v is not None}
        return price_map

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

    def simulate(self, start: date, end: date, params: SimulationParams, manual_symbols: Optional[List[str]] = None) -> SimulationRun:
        start_date = _to_date(start)
        end_date = _to_date(end)
        manual_syms = {s.upper() for s in (manual_symbols or []) if s}

        # preload prices for the window to avoid repeated parquet scans
        self._price_cache = {}
        self._build_price_cache_from_prices(start_date, end_date)

        open_positions: Dict[str, Dict[str, object]] = {}
        closed: List[TradeResult] = []
        seen_symbols: set[str] = set()

        for day in _date_range(start_date, end_date):
            candidates = self._candidate_rows_for_day(day, params)
            candidate_price_map = {str(r.get("symbol") or "").upper(): r.get("price") for r in candidates if r.get("symbol")}
            daily_price_map = self._price_map_for_day(day, candidate_price_map.keys())
            for row in candidates:
                sym = str(row.get("symbol") or "").upper()
                if not sym:
                    continue
                if params.first_trade_only and sym in seen_symbols:
                    continue
                if sym in open_positions:
                    continue
                open_positions[sym] = {
                    "entry_date": day,
                    "entry_price": row["price"],
                    "last_price": row["price"],
                }
                seen_symbols.add(sym)

            # allow manual injections on start day
            if manual_syms and day == start_date:
                for sym in manual_syms:
                    if params.first_trade_only and sym in seen_symbols:
                        continue
                    if sym not in open_positions:
                        price_today = daily_price_map.get(sym)
                        open_positions[sym] = {
                            "entry_date": day,
                            "entry_price": price_today,
                            "last_price": price_today,
                        }
                        seen_symbols.add(sym)

            # price map for exit checks (use daily prices, not just candidates)
            price_map = {**daily_price_map, **candidate_price_map}
            to_exit: List[Tuple[str, TradeResult]] = []
            for sym, pos in open_positions.items():
                price_today = price_map.get(sym, pos.get("last_price"))
                if price_today is None:
                    continue
                pos["last_price"] = price_today
                entry_price = pos.get("entry_price") or price_today
                entry_date = pos["entry_date"]
                holding_days = (day - entry_date).days
                stop_price = entry_price * (1 - params.stop_loss_pct) if params.stop_loss_pct else None

                stop_hit = stop_price is not None and price_today <= stop_price
                timed_out = params.max_hold_days is not None and holding_days >= int(params.max_hold_days)
                if stop_hit or timed_out or day == end_date:
                    exit_reason = "timeout" if timed_out else "stop" if stop_hit else "close"
                    pnl_pct = ((price_today - entry_price) / entry_price) * 100 if entry_price else 0.0
                    to_exit.append(
                        (
                            sym,
                            TradeResult(
                                symbol=sym,
                                entry_date=entry_date,
                                exit_date=day,
                                entry_price=float(entry_price),
                                exit_price=float(price_today),
                                pnl_pct=float(pnl_pct),
                                holding_days=holding_days,
                                notes=exit_reason,
                            ),
                        )
                    )
            for sym, trade in to_exit:
                closed.append(trade)
                open_positions.pop(sym, None)

        symbols_for_chart = {t.symbol for t in closed}
        chart_start = start_date - timedelta(days=30)
        chart_end = end_date + timedelta(days=30)
        # extend cache range so charts have prices pre/post window
        self._build_price_cache_from_prices(chart_start, chart_end)
        charts = self._series_from_cache(symbols_for_chart, chart_start, chart_end)

        pnl_values = [t.pnl_pct for t in closed]
        avg_return = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0
        win_rate = sum(1 for p in pnl_values if p > 0) / len(pnl_values) * 100 if pnl_values else 0.0
        total_return = sum(pnl_values) if pnl_values else 0.0
        summary = {
            "trades": float(len(closed)),
            "avg_return_pct": float(avg_return),
            "win_rate_pct": float(win_rate),
            "total_return_pct": float(total_return),
        }

        return SimulationRun(
            label="baseline",
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
        manual_symbols: Optional[List[str]] = None,
    ) -> List[SimulationRun]:
        runs: List[SimulationRun] = [self.simulate(start, end, base_params, manual_symbols)]
        for label, variant in variants or []:
            runs.append(self.simulate(start, end, variant, manual_symbols))
        runs.sort(key=lambda r: r.summary.get("avg_return_pct", 0), reverse=True)
        return runs
