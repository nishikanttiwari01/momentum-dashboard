from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.repos.models import CandidatePool


class CandidatePoolRepo:
    def __init__(self, session: Session | None = None):
        self.s = session

    # ----- internal helpers -----
    def _session(self) -> Session:
        if self.s is None:
            raise RuntimeError("CandidatePoolRepo requires a session")
        return self.s

    @staticmethod
    def _canon_symbol(symbol: str) -> str:
        return symbol.upper()

    @staticmethod
    def _aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    # ----- reads -----
    def list_entries(self, *, active_only: bool = True) -> List[Dict[str, Any]]:
        if self.s is None:
            return []
        q = self.s.query(CandidatePool)
        if active_only:
            q = q.filter(CandidatePool.status == "ACTIVE")
        rows: Iterable[CandidatePool] = (
            q.order_by(
                CandidatePool.rank_ord.is_(None),  # False (0) before True (1)
                CandidatePool.rank_ord.asc(),
                CandidatePool.rank_score.desc(),
                CandidatePool.added_at.asc(),
            ).all()
        )
        return [self._row_to_dict(r) for r in rows]

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self.s is None:
            return None
        row = (
            self.s.query(CandidatePool)
            .filter(CandidatePool.symbol == self._canon_symbol(symbol))
            .one_or_none()
        )
        return self._row_to_dict(row) if row else None

    # ----- writes -----
    def upsert(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        session = self._session()
        symbol = self._canon_symbol(entry.get("symbol", ""))
        now = datetime.utcnow()
        row = (
            session.query(CandidatePool)
            .filter(CandidatePool.symbol == symbol)
            .one_or_none()
        )
        if row is None:
            row = CandidatePool(symbol=symbol)
            session.add(row)

        # required core fields
        row.symbol = symbol
        row.status = entry.get("status") or row.status or "ACTIVE"
        row.rank_ord = entry.get("rank_ord")
        row.rank_score = entry.get("rank_score")

        # lifecycle
        row.added_at = entry.get("added_at") or row.added_at or now
        row.added_date = entry.get("added_date") or row.added_date
        row.added_run_id = entry.get("added_run_id") or row.added_run_id
        row.added_as_of = entry.get("added_as_of") or row.added_as_of

        row.last_seen_at = entry.get("last_seen_at") or now
        row.last_seen_run_id = entry.get("last_seen_run_id") or row.last_seen_run_id
        row.last_seen_as_of = entry.get("last_seen_as_of") or row.last_seen_as_of
        row.last_price = entry.get("last_price")
        row.last_score = entry.get("last_score")
        row.last_adx14 = entry.get("last_adx14")
        row.last_atr_pct = entry.get("last_atr_pct")
        row.last_r_multiple = entry.get("last_r_multiple")
        row.last_prox_52w_high_pct = entry.get("last_prox_52w_high_pct")
        row.last_liquidity = entry.get("last_liquidity")
        row.last_ema20 = entry.get("last_ema20")

        row.exit_reason = entry.get("exit_reason")
        row.removed_at = entry.get("removed_at") or row.removed_at
        row.removed_run_id = entry.get("removed_run_id") or row.removed_run_id
        row.reasons_json = entry.get("reasons_json") or entry.get("reasons")

        session.flush()
        session.commit()
        return self._row_to_dict(row)

    def mark_removed(
        self,
        symbol: str,
        *,
        reason: str | None = None,
        removed_at: datetime | None = None,
        run_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        session = self._session()
        row = (
            session.query(CandidatePool)
            .filter(CandidatePool.symbol == self._canon_symbol(symbol))
            .one_or_none()
        )
        if row is None:
            return None
        row.status = "REMOVED"
        row.exit_reason = reason or row.exit_reason
        row.removed_at = removed_at or datetime.utcnow()
        row.removed_run_id = run_id or row.removed_run_id
        session.flush()
        session.commit()
        return self._row_to_dict(row)

    # ----- helpers -----
    def _row_to_dict(self, r: CandidatePool | None) -> Optional[Dict[str, Any]]:
        if r is None:
            return None
        return {
            "id": r.id,
            "symbol": r.symbol,
            "added_at": self._aware(r.added_at),
            "added_date": r.added_date,
            "added_run_id": r.added_run_id,
            "added_as_of": r.added_as_of,
            "last_seen_at": self._aware(r.last_seen_at),
            "last_seen_run_id": r.last_seen_run_id,
            "last_seen_as_of": r.last_seen_as_of,
            "last_price": r.last_price,
            "last_score": r.last_score,
            "last_adx14": r.last_adx14,
            "last_atr_pct": r.last_atr_pct,
            "last_r_multiple": r.last_r_multiple,
            "last_prox_52w_high_pct": r.last_prox_52w_high_pct,
            "last_liquidity": r.last_liquidity,
            "last_ema20": r.last_ema20,
            "rank_score": r.rank_score,
            "rank_ord": r.rank_ord,
            "status": r.status,
            "exit_reason": r.exit_reason,
            "removed_at": self._aware(r.removed_at),
            "removed_run_id": r.removed_run_id,
            "reasons": r.reasons_json if isinstance(r.reasons_json, (list, dict)) else None,
        }


# Back-compat alias
SqlCandidatePoolRepo = CandidatePoolRepo
