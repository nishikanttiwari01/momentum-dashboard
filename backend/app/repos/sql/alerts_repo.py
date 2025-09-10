from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import Alert
from ..interfaces.base import IAlertsRepo, AlertRuleVO


class SqlAlertsRepo(IAlertsRepo):
    def __init__(self, session: Session):
        self.s = session

    def list_alerts(self) -> list[AlertRuleVO]:
        rows = self.s.query(Alert).order_by(Alert.symbol.asc(), Alert.id.asc()).all()
        return [
            AlertRuleVO(
                id=r.id,
                symbol=r.symbol,
                rule_type=r.rule_type,
                rule_value=r.rule_value,
                channels=r.channels or [],
                enabled=r.enabled,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    def create_alert(self, rule: AlertRuleVO) -> AlertRuleVO:
        now = datetime.utcnow()
        row = Alert(
            symbol=rule.symbol.upper(),
            rule_type=rule.rule_type,
            rule_value=rule.rule_value,
            channels=list(rule.channels or []),
            enabled=bool(rule.enabled),
        )
        self.s.add(row)
        self.s.flush()
        rule.id = row.id
        rule.created_at = row.created_at or now
        rule.updated_at = row.updated_at or now
        return rule

    def enable_alert(self, alert_id: int, enabled: bool) -> None:
        self.s.query(Alert).filter(Alert.id == alert_id).update(
            {"enabled": bool(enabled)},
            synchronize_session=False,
        )
