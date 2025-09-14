from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    status: str  # PENDING | RUNNING | SUCCEEDED | FAILED
    started_at: str
    finished_at: Optional[str] = None
    rows_computed: Optional[int] = None
    duration_ms: Optional[int] = None

class RunDetail(RunSummary):
    key: Optional[str] = None
    snapshot_path: Optional[str] = None
    as_of: Optional[str] = None
    error_json: Optional[dict] = None

class RunsList(BaseModel):
    items: list[RunSummary] = Field(default_factory=list)
