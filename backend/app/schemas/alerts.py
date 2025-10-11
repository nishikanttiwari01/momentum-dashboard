from __future__ import annotations
from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class AlertRuleCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    rule_type: str = Field(..., min_length=1, max_length=32)
    rule_value: Optional[str] = Field(None, max_length=64)
    channels: List[str] = Field(default_factory=list)
    enabled: bool = True


class AlertRuleOut(BaseModel):
    id: int
    symbol: str
    rule_type: str
    rule_value: Optional[str]
    channels: List[str]
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class AlertRuleSummary(BaseModel):
    symbol: str
    rule_type: str
    rule_value: Optional[str] = None
    channels: List[str] = Field(default_factory=list)
    enabled: bool = True
    conditions: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra='allow')


class AlertStateOut(BaseModel):
    id: Optional[int] = None
    rule: AlertRuleSummary
    last_fired_at: Optional[datetime] = None
    muted_until: Optional[datetime] = None
    last_score: Optional[int] = None
    last_fired_local_date: Optional[date] = None
    last_fired_run_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
