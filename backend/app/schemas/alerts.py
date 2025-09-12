from __future__ import annotations
from typing import List, Optional
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


