from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, status
from app.schemas.alerts import AlertRuleCreate, AlertRuleOut
from app.core.db import get_sessionmaker
from app.repos.unit_of_work import SqliteUnitOfWork
from app.repos.interfaces.base import AlertRuleVO

router = APIRouter()


def get_uow():
    return SqliteUnitOfWork(get_sessionmaker())


@router.get("/alerts", response_model=List[AlertRuleOut])
def list_alerts(uow: SqliteUnitOfWork = Depends(get_uow)):
    with uow:
        rules = uow.alerts.list_alerts()
        return rules


@router.post("/alerts", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_alert(rule: AlertRuleCreate, uow: SqliteUnitOfWork = Depends(get_uow)):
    vo = AlertRuleVO(
        id=None,
        symbol=rule.symbol.upper(),
        rule_type=rule.rule_type,
        rule_value=rule.rule_value,
        channels=rule.channels,
        enabled=rule.enabled,
        created_at=None,
        updated_at=None,
    )
    with uow:
        saved = uow.alerts.create_alert(vo)
        return saved
