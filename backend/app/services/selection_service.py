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
    liquidity: Optional[float]
    price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    r_multiple: Optional[float]
    risk_pct: Optional[float]
    position_size_pct: Optional[float]
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
    position_size_pct: float = 0.0  # fraction of portfolio (e.g. 0.20 = 20%)


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
    """Return (stop, target, r_multiple, risk_pct).

    Target is now R-ratio based (entry + N × risk) when r_ratio_target is
    configured, which ensures R:R is always controlled regardless of ATR size.
    Falls back to fixed t1_gain_pct for backwards compatibility.
    """
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

    risk = price - stop_candidate
    if risk <= 0:
        return (None, None, None, None)

    # R-ratio target: target = entry + r_ratio × risk (adaptive, preferred).
    # Ensures that whether ATR is 2% or 6%, the reward is always N× the risk.
    r_ratio = _safe_float(getattr(sell_cfg.targets, "r_ratio_target", None))
    if r_ratio is not None and r_ratio > 0:
        target_price = price + risk * r_ratio
    else:
        t1_pct = sell_cfg.targets.t1_gain_pct
        target_price = price * (1 + float(t1_pct) / 100.0)

    reward = target_price - price
    if reward <= 0:
        return (None, None, None, None)
    r_multiple = reward / risk
    risk_pct = (risk / price) * 100.0
    return (stop_candidate, target_price, r_multiple, risk_pct)


def _compute_position_size(
    *,
    price: float,
    stop_price: float,
    risk_pct_per_trade: float = 1.5,
    max_position_pct: float = 40.0,
) -> float:
    """Return position size as % of portfolio (0-100 scale).

    Sizes so that a full stop hit costs exactly risk_pct_per_trade% of portfolio.
    Capped at max_position_pct% to prevent over-concentration.
    """
    if price <= 0 or stop_price <= 0 or stop_price >= price:
        return 0.0
    risk_per_unit_pct = (price - stop_price) / price * 100.0
    if risk_per_unit_pct <= 0:
        return 0.0
    raw_pct = risk_pct_per_trade / risk_per_unit_pct * 100.0
    return min(raw_pct, max_position_pct)


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


def _positions_counting_toward_limit(positions: Iterable[Dict[str, Any]]) -> int:
    """
    Count both active trades and locked-but-not-closed selections.
    A slot should stay occupied until the position is explicitly sold/closed.
    """
    total = 0
    for pos in positions:
        if pos.get("sold_at") is None:
            total += 1
    return total


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
    risk_pct_per_trade = float(
        getattr(strategy.selection_policy, "risk_pct_per_trade", 1.5) or 1.5
    )
    position_size_pct = _compute_position_size(
        price=price,
        stop_price=stop_price,
        risk_pct_per_trade=risk_pct_per_trade,
    )
    return SelectionCandidate(
        symbol=str(row.get("symbol")).upper(),
        sector=row.get("sector"),
        score=_safe_float(row.get("score")),
        liquidity=_safe_float(row.get("liquidity") or row.get("median_traded_value_20d")),
        price=price,
        stop_price=stop_price,
        target_price=target_price,
        r_multiple=r_multiple,
        risk_pct=risk_pct,
        position_size_pct=position_size_pct,
        row=row,
    )


def _dense_rank_desc(values: Dict[str, float]) -> Dict[str, int]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ranks: Dict[str, int] = {}
    current_rank = 0
    last_value: Optional[float] = None
    for idx, (symbol, value) in enumerate(ordered, start=1):
        if last_value is None or value != last_value:
            current_rank = idx
            last_value = value
        ranks[symbol] = current_rank
    return ranks


def _candidate_sort_key(
    candidate: SelectionCandidate,
    *,
    policy: StrategySelectionPolicyConfig,
    weighted_scores: Optional[Dict[str, float]] = None,
) -> Tuple[float, float, float, str]:
    tiebreaker = str(getattr(policy, "tiebreaker", "") or "").strip().lower()
    if tiebreaker in {"weighted_composite", "weighted_score_r_multiple_liquidity"} and weighted_scores:
        return (
            -(weighted_scores.get(candidate.symbol) or 0.0),
            -(candidate.score or 0.0),
            -(candidate.r_multiple or 0.0),
            candidate.symbol,
        )
    return (
        -(candidate.r_multiple or 0.0),
        -(candidate.score or 0.0),
        -(candidate.liquidity or 0.0),
        candidate.symbol,
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
    all_positions = _list_positions(repo)
    if policy.max_open_positions is not None and policy.max_open_positions > 0:
        if _positions_counting_toward_limit(all_positions) >= policy.max_open_positions:
            return None

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

    weighted_scores: Optional[Dict[str, float]] = None
    tiebreaker = str(getattr(policy, "tiebreaker", "") or "").strip().lower()
    if tiebreaker in {"weighted_composite", "weighted_score_r_multiple_liquidity"}:
        score_ranks = _dense_rank_desc({c.symbol: c.score or 0.0 for c, _ in candidates})
        r_multiple_ranks = _dense_rank_desc({c.symbol: c.r_multiple or 0.0 for c, _ in candidates})
        liquidity_ranks = _dense_rank_desc({c.symbol: c.liquidity or 0.0 for c, _ in candidates})
        weighted_scores = {}
        for candidate, _ in candidates:
            weighted_scores[candidate.symbol] = (
                (0.5 / float(score_ranks.get(candidate.symbol) or len(candidates)))
                + (0.3 / float(r_multiple_ranks.get(candidate.symbol) or len(candidates)))
                + (0.2 / float(liquidity_ranks.get(candidate.symbol) or len(candidates)))
            )

    candidates.sort(
        key=lambda item: _candidate_sort_key(
            item[0],
            policy=policy,
            weighted_scores=weighted_scores,
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

    if tiebreaker in {"weighted_composite", "weighted_score_r_multiple_liquidity"} and weighted_scores:
        weighted_score = weighted_scores.get(best.symbol) or 0.0
        reason = (
            f"Weighted {weighted_score:.3f}; "
            f"Score {best.score or 'NA'}; "
            f"R {best.r_multiple:.2f}; "
            f"Size {best.position_size_pct or 0:.1f}%; "
            f"Liq {best.liquidity or 0:.0f}"
        )
    else:
        reason = (
            f"R {best.r_multiple:.2f}; "
            f"Score {best.score or 'NA'}; "
            f"Size {best.position_size_pct or 0:.1f}%"
        )
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
        position_size_pct=best.position_size_pct or 0.0,
    )


def apply_selection_policy_multi(
    *,
    session: Session,
    rows: List[Dict[str, Any]],
    strategy: StrategyConfig,
    policy: StrategySelectionPolicyConfig,
    run_id: str,
    trading_day: date,
    nifty_regime: Optional[str],
    now_utc: datetime,
) -> List[SelectionResult]:
    """Return up to ``policy.top_n_per_run`` picks in one screening pass.

    Honors the same gates as the single-pick variant (regime, weekly_quota,
    max_open_positions, symbol/sector cooldown) and additionally enforces
    ``policy.max_per_sector_per_run`` across the picks produced in *this* run
    so one sector doesn't sweep the slate.

    Safe to call for callers that want a list — the old single-pick
    ``apply_selection_policy`` is preserved for back-compat.
    """
    if not policy.apply_at_selection:
        return []
    if not _regime_allows_selection(policy, nifty_regime):
        return []

    top_n = int(getattr(policy, "top_n_per_run", 1) or 1)
    if top_n <= 0:
        top_n = 1
    max_per_sector = int(getattr(policy, "max_per_sector_per_run", 1) or 1)
    if max_per_sector <= 0:
        max_per_sector = top_n  # disable the cap if misconfigured

    repo = PositionsRepo(session=session)
    all_positions = _list_positions(repo)
    if policy.max_open_positions is not None and policy.max_open_positions > 0:
        existing_count = _positions_counting_toward_limit(all_positions)
        if existing_count >= policy.max_open_positions:
            return []
        remaining_open_slots = policy.max_open_positions - existing_count
    else:
        remaining_open_slots = top_n

    if policy.weekly_quota is not None and policy.weekly_quota > 0:
        weekly_count = _weekly_selection_count(all_positions, _iso_year_week(trading_day))
        remaining_weekly = policy.weekly_quota - weekly_count
        if remaining_weekly <= 0:
            return []
    else:
        remaining_weekly = top_n

    budget = min(top_n, remaining_open_slots, remaining_weekly)
    if budget <= 0:
        return []

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
        return []

    weighted_scores: Optional[Dict[str, float]] = None
    tiebreaker = str(getattr(policy, "tiebreaker", "") or "").strip().lower()
    if tiebreaker in {"weighted_composite", "weighted_score_r_multiple_liquidity"}:
        score_ranks = _dense_rank_desc({c.symbol: c.score or 0.0 for c, _ in candidates})
        r_multiple_ranks = _dense_rank_desc({c.symbol: c.r_multiple or 0.0 for c, _ in candidates})
        liquidity_ranks = _dense_rank_desc({c.symbol: c.liquidity or 0.0 for c, _ in candidates})
        weighted_scores = {}
        for candidate, _ in candidates:
            weighted_scores[candidate.symbol] = (
                (0.5 / float(score_ranks.get(candidate.symbol) or len(candidates)))
                + (0.3 / float(r_multiple_ranks.get(candidate.symbol) or len(candidates)))
                + (0.2 / float(liquidity_ranks.get(candidate.symbol) or len(candidates)))
            )

    candidates.sort(
        key=lambda item: _candidate_sort_key(
            item[0],
            policy=policy,
            weighted_scores=weighted_scores,
        )
    )

    picks: List[SelectionResult] = []
    picked_symbols: set[str] = set()
    sector_counts: Dict[str, int] = {}
    for candidate, row_index in candidates:
        if len(picks) >= budget:
            break
        sym_upper = candidate.symbol.upper()
        if sym_upper in picked_symbols:
            continue
        sector_key = (candidate.sector or "_UNKNOWN").strip().upper() or "_UNKNOWN"
        if sector_counts.get(sector_key, 0) >= max_per_sector:
            continue

        note_payload = {
            "source": "selection_service",
            "selected_at": trading_day.isoformat(),
            "run_id": run_id,
            "sector": candidate.sector,
            "r_multiple": candidate.r_multiple,
            "stop": candidate.stop_price,
            "target": candidate.target_price,
            "pick_index": len(picks) + 1,
        }
        try:
            repo.create_or_lock(
                symbol=candidate.symbol,
                price=candidate.price,
                note=json.dumps(note_payload),
            )
        except Exception:
            # Persist failure on one pick should not block the remaining picks.
            pass

        if tiebreaker in {"weighted_composite", "weighted_score_r_multiple_liquidity"} and weighted_scores:
            weighted_score = weighted_scores.get(candidate.symbol) or 0.0
            reason = (
                f"Weighted {weighted_score:.3f}; "
                f"Score {candidate.score or 'NA'}; "
                f"R {candidate.r_multiple:.2f}; "
                f"Size {candidate.position_size_pct or 0:.1f}%; "
                f"Liq {candidate.liquidity or 0:.0f}"
            )
        else:
            reason = (
                f"R {candidate.r_multiple:.2f}; "
                f"Score {candidate.score or 'NA'}; "
                f"Size {candidate.position_size_pct or 0:.1f}%"
            )

        picks.append(
            SelectionResult(
                symbol=candidate.symbol,
                sector=candidate.sector,
                profile=candidate.row.get("buy_profile"),
                mode=candidate.row.get("buy_mode"),
                price=candidate.price or 0.0,
                stop_price=candidate.stop_price or 0.0,
                target_price=candidate.target_price or 0.0,
                r_multiple=candidate.r_multiple or 0.0,
                score=candidate.score,
                run_id=run_id,
                trading_date=trading_day,
                row_index=row_index,
                reason=reason,
                position_size_pct=candidate.position_size_pct or 0.0,
            )
        )
        picked_symbols.add(sym_upper)
        sector_counts[sector_key] = sector_counts.get(sector_key, 0) + 1

    return picks
