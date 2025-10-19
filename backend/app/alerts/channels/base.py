from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import logging

log = logging.getLogger(__name__)

@dataclass
class DeliveryResult:
    status: str  # SENT | FAILED | SKIPPED
    response_code: Optional[int] = None
    response_meta: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 1

    def __post_init__(self) -> None:
        log.debug(
            "DeliveryResult created status=%s code=%s attempts=%s meta_keys=%s",
            self.status,
            self.response_code,
            self.attempts,
            list(self.response_meta.keys()),
        )
