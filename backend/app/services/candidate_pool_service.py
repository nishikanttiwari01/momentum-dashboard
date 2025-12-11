from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import CandidatePoolConfig, StrategyConfig
from app.repos.sql.candidate_pool_repo import CandidatePoolRepo


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _normalize_map(values: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    valid = [v for v in values.values() if v is not None]
    if not valid:
        return {k: None for k in values}
    lo, hi = min(valid), max(valid)
    if hi - lo < 1e-9:
        return {k: 0.5 if v is not None else None for k, v in values.items()}
    return {k: ((v - lo) / (hi - lo)) if v is not None else None for k, v in values.items()}


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

    atr_value = price * (atr_pct / 100.0)
    atr_multiple = sell_cfg.stop.atr_multiple
    floor_pct = sell_cfg.stop.floor_pct

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


@dataclass
class PoolExitCheck:
    code: str
    label: str
    passed: bool
    value: float | None = None
    threshold: float | None = None
    note: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "pass": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "note": self.note,
        }


@dataclass
class PoolEntry:
    symbol: str
    added_at: datetime
    added_date: date | None
    added_run_id: str | None
    added_as_of: str | None
    last_seen_at: datetime
    last_seen_run_id: str | None
    last_seen_as_of: str | None
    last_price: float | None
    score: float | None
    adx14: float | None
    atr_pct: float | None
    r_multiple: float | None
    prox52w: float | None
    liquidity: float | None
    ema20: float | None
    db_status: str = "ACTIVE"
    exit_reason: str | None = None
    rank_score: float | None = None
    rank_ord: int | None = None
    reasons: list[str] = field(default_factory=list)
    exit_checks: list[PoolExitCheck] = field(default_factory=list)
    stale: bool = False

    def to_repo_payload(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "added_at": self.added_at,
            "added_date": self.added_date,
            "added_run_id": self.added_run_id,
            "added_as_of": self.added_as_of,
            "last_seen_at": self.last_seen_at,
            "last_seen_run_id": self.last_seen_run_id,
            "last_seen_as_of": self.last_seen_as_of,
            "last_price": self.last_price,
            "last_score": self.score,
            "last_adx14": self.adx14,
            "last_atr_pct": self.atr_pct,
            "last_r_multiple": self.r_multiple,
            "last_prox_52w_high_pct": self.prox52w,
            "last_liquidity": self.liquidity,
            "last_ema20": self.ema20,
            "rank_score": self.rank_score,
            "rank_ord": self.rank_ord,
            "status": self.db_status,
            "exit_reason": self.exit_reason,
            "reasons": [r for r in self.reasons if r],
            "reasons_json": [r for r in self.reasons if r],
        }


@dataclass
class PoolSyncResult:
    entries: List[PoolEntry]
    added: List[str]
    removed: List[Tuple[str, str | None]]
    selected: Optional[PoolEntry]
    as_of: Optional[str]
    run_id: Optional[str]


class CandidatePoolService:
    def __init__(
        self,
        *,
        repo: CandidatePoolRepo,
        cfg: CandidatePoolConfig,
        strategy: StrategyConfig,
    ):
        self.repo = repo
        self.cfg = cfg or CandidatePoolConfig()
        self.strategy = strategy

    # -------- main entrypoint --------
    def sync(
        self,
        *,
        rows_by_symbol: Dict[str, Dict[str, Any]],
        now_utc: datetime,
        run_id: str,
        as_of: Optional[str],
        trading_day: date,
        is_eod_snapshot: bool,
    ) -> PoolSyncResult:
        existing = self.repo.list_entries(active_only=False)
        existing_map: Dict[str, PoolEntry] = {}
        for row in existing:
            entry = self._entry_from_repo(row, now_utc)
            existing_map[entry.symbol] = entry

        added_symbols: List[str] = []
        removed_symbols: List[Tuple[str, str | None]] = []

        # Update metrics for entries seen in this run
        seen_symbols: set[str] = set()
        for symbol_raw, row in rows_by_symbol.items():
            symbol = (symbol_raw or "").upper()
            seen_symbols.add(symbol)
            if symbol in existing_map:
                self._update_entry_from_row(
                    entry=existing_map[symbol],
                    row=row,
                    now_utc=now_utc,
                    run_id=run_id,
                    as_of=as_of,
                )

        # Determine new candidates (strict EOD adds only)
        if is_eod_snapshot:
            for symbol_raw, row in rows_by_symbol.items():
                symbol = (symbol_raw or "").upper()
                if symbol in existing_map:
                    continue
                if not bool(row.get("buy_flag")):
                    continue
                entry = self._entry_from_row(
                    symbol=symbol,
                    row=row,
                    now_utc=now_utc,
                    run_id=run_id,
                    as_of=as_of,
                    trading_day=trading_day,
                )
                existing_map[symbol] = entry
                added_symbols.append(symbol)

        # Evaluate exit checks (remove only on EOD)
        active_entries: List[PoolEntry] = []
        for entry in existing_map.values():
            checks, notes = self._exit_checks(entry, trading_day)
            entry.exit_checks = checks
            entry.reasons = notes

            if entry.db_status == "REMOVED":
                continue

            should_remove = is_eod_snapshot and any(not c.passed for c in checks)
            if should_remove:
                entry.db_status = "REMOVED"
                entry.exit_reason = self._exit_reason_from_checks(checks)
                self.repo.mark_removed(
                    entry.symbol,
                    reason=entry.exit_reason,
                    removed_at=now_utc,
                    run_id=run_id,
                )
                removed_symbols.append((entry.symbol, entry.exit_reason))
            else:
                active_entries.append(entry)

        # Ranking + max-size enforcement
        ranked_entries = self._rank_entries(active_entries)
        ranked_entries.sort(
            key=lambda e: (
                -(e.rank_score or 0.0),
                -(e.score or 0.0),
                e.symbol,
            )
        )
        kept = ranked_entries[: max(1, int(self.cfg.max_size or 10))]
        # Any active entry dropped due to max_size should be marked removed
        dropped = {e.symbol for e in ranked_entries[len(kept) :]}
        for sym in dropped:
            if sym in existing_map:
                existing_map[sym].db_status = "REMOVED"
                existing_map[sym].exit_reason = "replaced"
            self.repo.mark_removed(sym, reason="replaced", removed_at=now_utc, run_id=run_id)
            removed_symbols.append((sym, "replaced"))

        # Persist kept entries with rank_ord
        for idx, entry in enumerate(kept, start=1):
            entry.rank_ord = idx
            entry.db_status = "ACTIVE"
            self.repo.upsert(entry.to_repo_payload())

        selected_entry = kept[0] if (kept and is_eod_snapshot) else None

        # Record daily history AFTER final ranks/removals
        try:
            self.repo.record_history(trading_day, existing_map.values())
        except Exception:
            pass

        # Purge REMOVED rows immediately now that history is persisted
        try:
            self.repo.purge_removed(older_than_days=0)
        except Exception:
            pass

        return PoolSyncResult(
            entries=kept,
            added=added_symbols,
            removed=removed_symbols,
            selected=selected_entry,
            as_of=as_of,
            run_id=run_id,
        )

    # -------- helpers --------
    def _entry_from_repo(self, data: Dict[str, Any], now_utc: datetime) -> PoolEntry:
        added_at = data.get("added_at") or now_utc
        if isinstance(added_at, str):
            try:
                added_at = datetime.fromisoformat(added_at)
            except Exception:
                added_at = now_utc
        last_seen_at = data.get("last_seen_at") or now_utc
        if isinstance(last_seen_at, str):
            try:
                last_seen_at = datetime.fromisoformat(last_seen_at)
            except Exception:
                last_seen_at = now_utc
        return PoolEntry(
            symbol=str(data.get("symbol") or "").upper(),
            added_at=added_at if added_at.tzinfo else added_at.replace(tzinfo=timezone.utc),
            added_date=data.get("added_date"),
            added_run_id=data.get("added_run_id"),
            added_as_of=data.get("added_as_of"),
            last_seen_at=last_seen_at if last_seen_at.tzinfo else last_seen_at.replace(tzinfo=timezone.utc),
            last_seen_run_id=data.get("last_seen_run_id"),
            last_seen_as_of=data.get("last_seen_as_of"),
            last_price=_safe_float(data.get("last_price")),
            score=_safe_float(data.get("last_score")),
            adx14=_safe_float(data.get("last_adx14")),
            atr_pct=_safe_float(data.get("last_atr_pct")),
            r_multiple=_safe_float(data.get("last_r_multiple")),
            prox52w=_safe_float(data.get("last_prox_52w_high_pct")),
            liquidity=_safe_float(data.get("last_liquidity")),
            ema20=_safe_float(data.get("last_ema20")),
            db_status=data.get("status") or "ACTIVE",
            exit_reason=data.get("exit_reason"),
            rank_score=_safe_float(data.get("rank_score")),
            rank_ord=data.get("rank_ord"),
            reasons=list(data.get("reasons") or []),
            exit_checks=[],
            stale=True,
        )

    def _entry_from_row(
        self,
        *,
        symbol: str,
        row: Dict[str, Any],
        now_utc: datetime,
        run_id: str,
        as_of: Optional[str],
        trading_day: date,
    ) -> PoolEntry:
        price = _safe_float(row.get("last"))
        r_mult = self._compute_r_multiple(row=row, price=price)
        return PoolEntry(
            symbol=symbol,
            added_at=now_utc,
            added_date=trading_day,
            added_run_id=run_id,
            added_as_of=as_of,
            last_seen_at=now_utc,
            last_seen_run_id=run_id,
            last_seen_as_of=as_of,
            last_price=price,
            score=_safe_float(row.get("score")),
            adx14=_safe_float(row.get("adx14")),
            atr_pct=_safe_float(row.get("atr10_pct") or row.get("atr_pct") or row.get("atr14_pct")),
            r_multiple=r_mult,
            prox52w=_safe_float(row.get("proximity_52w_high_pct") or row.get("pct_from_52w_high")),
            liquidity=_safe_float(row.get("liquidity") or row.get("median_traded_value_20d")),
            ema20=_safe_float(row.get("ema20")),
            db_status="ACTIVE",
        )

    def _update_entry_from_row(
        self,
        *,
        entry: PoolEntry,
        row: Dict[str, Any],
        now_utc: datetime,
        run_id: str,
        as_of: Optional[str],
    ) -> None:
        price = _safe_float(row.get("last"))
        entry.last_seen_at = now_utc
        entry.last_seen_run_id = run_id
        entry.last_seen_as_of = as_of or entry.last_seen_as_of
        entry.last_price = price if price is not None else entry.last_price
        entry.score = _safe_float(row.get("score")) or entry.score
        entry.adx14 = _safe_float(row.get("adx14")) or entry.adx14
        entry.atr_pct = _safe_float(row.get("atr10_pct") or row.get("atr_pct") or row.get("atr14_pct")) or entry.atr_pct
        entry.r_multiple = self._compute_r_multiple(row=row, price=price) or entry.r_multiple
        entry.prox52w = _safe_float(row.get("proximity_52w_high_pct") or row.get("pct_from_52w_high")) or entry.prox52w
        entry.liquidity = _safe_float(row.get("liquidity") or row.get("median_traded_value_20d")) or entry.liquidity
        entry.ema20 = _safe_float(row.get("ema20")) or entry.ema20
        entry.stale = False

    def _compute_r_multiple(self, *, row: Dict[str, Any], price: Optional[float]) -> Optional[float]:
        if price is None or price <= 0:
            return None
        _, _, r_multiple, _ = _compute_stop_target(row, price=price, strategy=self.strategy)
        return r_multiple

    def _exit_checks(self, entry: PoolEntry, trading_day: date) -> Tuple[List[PoolExitCheck], List[str]]:
        cfg = self.cfg.exit_rules
        checks: List[PoolExitCheck] = []
        reasons: List[str] = []
        warnings: List[str] = []

        # EMA20 (if available)
        if cfg.require_above_ema20:
            if entry.last_price is not None and entry.ema20 is not None:
                diff_pct = ((entry.last_price / entry.ema20) - 1.0) * 100.0
                passed = diff_pct >= 0
                checks.append(
                    PoolExitCheck(
                        code="ema20",
                        label="Above EMA20",
                        passed=passed,
                        value=diff_pct,
                        threshold=0.0,
                        note="Close vs EMA20 (%)",
                    )
                )
                if passed and diff_pct <= 1.5:
                    warnings.append("Near EMA20")
                if not passed:
                    reasons.append("Below EMA20")
            else:
                checks.append(PoolExitCheck(code="ema20", label="Above EMA20", passed=True, value=None, threshold=0.0))

        # ADX
        adx_val = entry.adx14
        adx_pass = True
        if adx_val is not None and cfg.min_adx14 is not None:
            adx_pass = adx_val >= cfg.min_adx14
            checks.append(
                PoolExitCheck(
                    code="adx14",
                    label="ADX14",
                    passed=adx_pass,
                    value=adx_val,
                    threshold=float(cfg.min_adx14),
                )
            )
            if adx_pass and adx_val < (cfg.min_adx14 + 2.0):
                warnings.append("ADX near floor")
            if not adx_pass:
                reasons.append(f"ADX14<{cfg.min_adx14}")
        else:
            checks.append(PoolExitCheck(code="adx14", label="ADX14", passed=True, value=adx_val, threshold=float(cfg.min_adx14)))

        # Proximity to 52W high
        prox_val = entry.prox52w
        prox_pass = True
        if prox_val is not None and cfg.min_prox52w_pct is not None:
            prox_pass = prox_val >= cfg.min_prox52w_pct
            checks.append(
                PoolExitCheck(
                    code="prox52w",
                    label="52W zone",
                    passed=prox_pass,
                    value=prox_val,
                    threshold=float(cfg.min_prox52w_pct),
                )
            )
            if prox_pass and prox_val < (cfg.min_prox52w_pct + 3.0):
                warnings.append("Far from 52W")
            if not prox_pass:
                reasons.append("Too far from 52W high")
        else:
            checks.append(
                PoolExitCheck(
                    code="prox52w",
                    label="52W zone",
                    passed=True,
                    value=prox_val,
                    threshold=float(cfg.min_prox52w_pct),
                )
            )

        # Age
        age_days = None
        try:
            if entry.added_date:
                age_days = (trading_day - entry.added_date).days
        except Exception:
            age_days = None
        if cfg.max_age_days and cfg.max_age_days > 0 and age_days is not None:
            age_pass = age_days <= cfg.max_age_days
            checks.append(
                PoolExitCheck(
                    code="age",
                    label="Age (days)",
                    passed=age_pass,
                    value=float(age_days),
                    threshold=float(cfg.max_age_days),
                )
            )
            if age_pass and age_days >= (cfg.max_age_days - 1):
                warnings.append("Aging out")
            if not age_pass:
                reasons.append("Stale > age limit")
        else:
            checks.append(
                PoolExitCheck(
                    code="age",
                    label="Age (days)",
                    passed=True,
                    value=float(age_days) if age_days is not None else None,
                    threshold=float(cfg.max_age_days) if cfg.max_age_days else None,
                )
            )

        status_notes = reasons if reasons else warnings
        return checks, status_notes

    def _exit_reason_from_checks(self, checks: List[PoolExitCheck]) -> str | None:
        for c in checks:
            if not c.passed:
                return c.code
        return None

    def _rank_entries(self, entries: List[PoolEntry]) -> List[PoolEntry]:
        if not entries:
            return []
        ranking = self.cfg.ranking
        weights = {
            "score": ranking.score_weight,
            "r_multiple": ranking.r_multiple_weight,
            "adx14": ranking.adx14_weight,
            "prox52w": ranking.prox52w_weight,
        }
        norm_score = _normalize_map({e.symbol: e.score for e in entries})
        norm_r = _normalize_map({e.symbol: e.r_multiple for e in entries})
        norm_adx = _normalize_map({e.symbol: e.adx14 for e in entries})
        norm_prox = _normalize_map({e.symbol: e.prox52w for e in entries})

        weight_total = sum(v for v in weights.values() if v is not None) or 1.0

        for e in entries:
            e.rank_score = (
                (norm_score.get(e.symbol) or 0.0) * weights["score"]
                + (norm_r.get(e.symbol) or 0.0) * weights["r_multiple"]
                + (norm_adx.get(e.symbol) or 0.0) * weights["adx14"]
                + (norm_prox.get(e.symbol) or 0.0) * weights["prox52w"]
            ) / weight_total
        return entries

    # -------- API helpers --------
    @staticmethod
    def serialize_entry(entry: PoolEntry, *, is_top: bool) -> Dict[str, Any]:
        status = "strong"
        if any(not chk.passed for chk in entry.exit_checks):
            status = "exit_soon"
        elif entry.reasons:
            status = "weakening"
        payload = {
            "symbol": entry.symbol,
            "rank": entry.rank_ord or 0,
            "rank_score": entry.rank_score,
            "added_on": entry.added_date.isoformat() if entry.added_date else entry.added_at.date().isoformat() if entry.added_at else None,
            "added_at": entry.added_at.isoformat() if entry.added_at else None,
            "added_run_id": entry.added_run_id,
            "added_as_of": entry.added_as_of,
            "last_seen_run_id": entry.last_seen_run_id,
            "last_seen_as_of": entry.last_seen_as_of,
            "last_price": entry.last_price,
            "score": entry.score,
            "adx14": entry.adx14,
            "atr_pct": entry.atr_pct,
            "r_multiple": entry.r_multiple,
            "prox_52w_high_pct": entry.prox52w,
            "liquidity": entry.liquidity,
            "ema20": entry.ema20,
            "status": status if entry.db_status == "ACTIVE" else "removed",
            "exit_checks": [chk.to_dict() for chk in entry.exit_checks],
            "reasons": entry.reasons,
            "stale": entry.stale,
            "is_top_candidate": is_top,
        }
        return payload
