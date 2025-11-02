from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import StrategyConfig, StrategySelectionPolicyConfig
from app.repos.sql.positions_repo import PositionsRepo


@dataclass
class SelectionCandidate:
    symbol: str
    sector: Optional[str]
    score: Optional[float]
    price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    r_multiple: Optional[float]
    risk_pct: Optional[float]
    row: Dict[str, Any]


@dataclass
class SelectionResult:
    symbol: str
    sector: Optional[str]
    profile: Optional[str]
    mode: Optional[str]
    price: float
    stop_price: float
    target_price: float
    r_multiple: float
    score: Optional[float]
    run_id: str
    trading_date: date
    row_index: int
    reason: str


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN check
        return None
    return f


def _compute_stop_target(
    row: Dict[str, Any],
    *,
    price: float,
    strategy: StrategyConfig,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    sell_cfg = strategy.profiles.sell.common
    atr_pct = (
        _safe_float(row.get("atr_pct"))
        or _safe_float(row.get("atr10_pct"))
        or _safe_float(row.get("atr14_pct"))
    )
    if atr_pct is None:
        return (None, None, None, None)

    atr_multiple = sell_cfg.stop.atr_multiple
    floor_pct = sell_cfg.stop.floor_pct

    atr_value = price * (atr_pct / 100.0)
    stop_candidate = price - (atr_value * atr_multiple)
    if floor_pct is not None:
        floor_price = price * (1 - float(floor_pct) / 100.0)
        stop_candidate = max(stop_candidate, floor_price)
    if stop_candidate <= 0 or stop_candidate >= price:
        return (None, None, None, None)

    t1_pct = sell_cfg.targets.t1_gain_pct
    target_price = price * (1 + float(t1_pct) / 100.0)
    risk = price - stop_candidate
    reward = target_price - price
    if risk <= 0 or reward <= 0:
        return (None, None, None, None)
    r_multiple = reward / risk
    risk_pct = (risk / price) * 100.0
    return (stop_candidate, target_price, r_multiple, risk_pct)


def _extract_sector_from_note(note: Optional[str]) -> Optional[str]:
    if not note:
        return None
    try:
        payload = json.loads(note)
    except Exception:
        return None
    if isinstance(payload, dict):
        sector = payload.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()
    return None


def _list_positions(repo: PositionsRepo) -> List[Dict[str, Any]]:
    try:
        return repo.list_positions()
    except Exception:
        return []


def _active_positions(repo: PositionsRepo) -> List[Dict[str, Any]]:
    try:
        return repo.list_positions(active=True)
    except Exception:
        return []


def _iso_year_week(day: date) -> Tuple[int, int]:
    return day.isocalendar()[0], day.isocalendar()[1]


def _within_days(reference: date, target: Optional[datetime], days: int) -> bool:
    if target is None:
        return False
    try:
        target_date = target.date()
    except Exception:
        return False
    delta = reference - target_date
    return delta.days is not None and 0 <= delta.days < days


def _enforce_symbol_cooldown(
    *,
    repo: PositionsRepo,
    symbol: str,
    trading_day: date,
    cooldown_days: int,
) -> bool:
    if cooldown_days <= 0:
        return True
    rows = repo.list_positions(symbol=symbol)
    if not rows:
        return True
    latest = max(
        (r.get("created_at") for r in rows if r.get("created_at")),
        default=None,
    )
    if latest is None:
        return True
    return not _within_days(trading_day, latest, cooldown_days)


def _enforce_sector_cooldown(
    *,
    positions: Iterable[Dict[str, Any]],
    sector: Optional[str],
    trading_day: date,
    cooldown_days: int,
) -> bool:
    if cooldown_days <= 0 or not sector:
        return True
    sector_norm = sector.strip().upper()
    for pos in positions:
        note_sector = _extract_sector_from_note(pos.get("note"))
        if note_sector and note_sector.strip().upper() == sector_norm:
            created_at = pos.get("created_at")
            if _within_days(trading_day, created_at, cooldown_days):
                return False
    return True


def _weekly_selection_count(
    positions: Iterable[Dict[str, Any]],
    trading_week: Tuple[int, int],
) -> int:
    year, week = trading_week
    count = 0
    for pos in positions:
        created_at = pos.get("created_at")
        if not isinstance(created_at, datetime):
            continue
        if _iso_year_week(created_at.date()) == (year, week):
            count += 1
    return count


def _regime_allows_selection(
    policy: StrategySelectionPolicyConfig,
    regime_value: Optional[str],
) -> bool:
    cfg = policy.regime
    if not cfg.enabled:
        return True
    if regime_value is None:
        return False
    regime_value = str(regime_value).upper()
    if cfg.require_index_above_fast and regime_value == "DOWN":
        return False
    if cfg.require_index_above_slow and regime_value not in {"UP"}:
        return False
    return True


def _candidate_from_row(
    row: Dict[str, Any],
    *,
    strategy: StrategyConfig,
) -> Optional[SelectionCandidate]:
    if not row.get("buy_flag"):
        return None
    price = _safe_float(row.get("last") or row.get("close"))
    if price is None or price <= 0:
        return None
    stop_price, target_price, r_multiple, risk_pct = _compute_stop_target(
        row,
        price=price,
        strategy=strategy,
    )
    if stop_price is None or target_price is None or r_multiple is None or r_multiple <= 0:
        return None
    return SelectionCandidate(
        symbol=str(row.get("symbol")).upper(),
        sector=row.get("sector"),
        score=_safe_float(row.get("score")),
        price=price,
        stop_price=stop_price,
        target_price=target_price,
        r_multiple=r_multiple,
        risk_pct=risk_pct,
        row=row,
    )


def apply_selection_policy(
    *,
    session: Session,
    rows: List[Dict[str, Any]],
    strategy: StrategyConfig,
    policy: StrategySelectionPolicyConfig,
    run_id: str,
    trading_day: date,
    nifty_regime: Optional[str],
    now_utc: datetime,
) -> Optional[SelectionResult]:
    if not policy.apply_at_selection:
        return None
    if not _regime_allows_selection(policy, nifty_regime):
        return None

    repo = PositionsRepo(session=session)
    active_positions = _active_positions(repo)
    if policy.max_open_positions is not None and policy.max_open_positions > 0:
        if len(active_positions) >= policy.max_open_positions:
            return None

    all_positions = _list_positions(repo)
    if policy.weekly_quota is not None and policy.weekly_quota > 0:
        weekly_count = _weekly_selection_count(all_positions, _iso_year_week(trading_day))
        if weekly_count >= policy.weekly_quota:
            return None

    candidates: List[Tuple[SelectionCandidate, int]] = []
    for idx, row in enumerate(rows):
        candidate = _candidate_from_row(row, strategy=strategy)
        if candidate is None:
            continue
        if not _enforce_symbol_cooldown(
            repo=repo,
            symbol=candidate.symbol,
            trading_day=trading_day,
            cooldown_days=policy.symbol_cooldown_days or 0,
        ):
            continue
        if not _enforce_sector_cooldown(
            positions=all_positions,
            sector=candidate.sector,
            trading_day=trading_day,
            cooldown_days=policy.sector_cooldown_days or 0,
        ):
            continue
        candidates.append((candidate, idx))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            -(item[0].r_multiple or 0.0),
            -(item[0].score or 0.0),
            item[0].symbol,
        )
    )
    best, row_index = candidates[0]

    note_payload = {
        "source": "selection_service",
        "selected_at": trading_day.isoformat(),
        "run_id": run_id,
        "sector": best.sector,
        "r_multiple": best.r_multiple,
        "stop": best.stop_price,
        "target": best.target_price,
    }
    try:
        repo.create_or_lock(
            symbol=best.symbol,
            price=best.price,
            note=json.dumps(note_payload),
        )
    except Exception:
        # Failure to persist position should not block further work.
        pass

    reason = f"R {best.r_multiple:.2f}; Score {best.score or 'NA'}"
    return SelectionResult(
        symbol=best.symbol,
        sector=best.sector,
        profile=best.row.get("buy_profile"),
        mode=best.row.get("buy_mode"),
        price=best.price or 0.0,
        stop_price=best.stop_price or 0.0,
        target_price=best.target_price or 0.0,
        r_multiple=best.r_multiple or 0.0,
        score=best.score,
        run_id=run_id,
        trading_date=trading_day,
        row_index=row_index,
        reason=reason,
    )
