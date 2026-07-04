from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repos.interfaces.base import AlertRuleVO
from app.repos.models import Alert


class SqlAlertsRepo:
    def __init__(self, session: Session):
        self.s = session

    def list_alerts(self) -> list[AlertRuleVO]:
        rows = (
            self.s.query(Alert)
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .all()
        )
        return [self._to_vo(row) for row in rows]

    def create_alert(self, rule: AlertRuleVO) -> AlertRuleVO:
        row = Alert(
            symbol=str(rule.symbol or "").upper(),
            rule_type=rule.rule_type,
            rule_value=rule.rule_value,
            channels=list(rule.channels or []),
            enabled=bool(rule.enabled),
        )
        self.s.add(row)
        self.s.flush()
        return self._to_vo(row)

    def enable_alert(self, alert_id: int, enabled: bool) -> None:
        row = self.s.query(Alert).filter(Alert.id == int(alert_id)).one_or_none()
        if row is None:
            return
        row.enabled = bool(enabled)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.s.flush()

    @staticmethod
    def _to_vo(row: Alert) -> AlertRuleVO:
        return AlertRuleVO(
            id=row.id,
            symbol=row.symbol,
            rule_type=row.rule_type,
            rule_value=row.rule_value,
            channels=list(row.channels or []),
            enabled=bool(row.enabled),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
