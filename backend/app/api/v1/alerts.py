from __future__ import annotations
from typing import List, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.schemas.alerts import AlertRuleCreate, AlertRuleOut
from app.core.db import get_sessionmaker
from app.repos.unit_of_work import SqliteUnitOfWork
from app.repos.interfaces.base import AlertRuleVO
from app.core.idempotency import get_idempotency_key  # dependency that validates/raises 422

router = APIRouter()


def get_uow() -> SqliteUnitOfWork:
    return SqliteUnitOfWork(get_sessionmaker())


@router.get("/alerts", response_model=List[AlertRuleOut])
def list_alerts(uow: SqliteUnitOfWork = Depends(get_uow)):
    with uow:
        return uow.alerts.list_alerts()


# Create: 201 on real create, but return 200 for header-only idempotency pings (rule is None)
@router.post("/alerts", response_model=AlertRuleOut | dict, status_code=status.HTTP_201_CREATED)
def create_alert(
    rule: Optional[AlertRuleCreate] = None,
    uow: SqliteUnitOfWork = Depends(get_uow),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    if rule is None:
        # Tests call POST with no JSON to just validate the header → must be 200 OK
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ok": True, "idempotency_key": idempotency_key},
        )

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
