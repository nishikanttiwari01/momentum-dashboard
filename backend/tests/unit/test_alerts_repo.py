from __future__ import annotations
from app.core.db import init_sqlite, get_sessionmaker
from app.repos.unit_of_work import SqliteUnitOfWork
from app.repos.interfaces.base import AlertRuleVO

def test_alerts_crud():
    init_sqlite("./data/test_alerts.db")
    uow = SqliteUnitOfWork(get_sessionmaker())
    with uow:
        created = uow.alerts.create_alert(
            AlertRuleVO(
                id=None,
                symbol="TCS",
                rule_type="price_crosses",
                rule_value="4200",
                channels=["desktop","email"],
                enabled=True,
                created_at=None,
                updated_at=None,
            )
        )
        assert created.id is not None
        items = uow.alerts.list_alerts()
        assert any(a.symbol == "TCS" for a in items)
        uow.alerts.enable_alert(created.id, False)
        items = uow.alerts.list_alerts()
        assert any((a.id == created.id and a.enabled is False) for a in items)
