from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class DeliveryResult:
    status: str  # SENT | FAILED | SKIPPED
    response_code: Optional[int] = None
    response_meta: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 1
