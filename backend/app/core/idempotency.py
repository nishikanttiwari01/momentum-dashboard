from __future__ import annotations
from typing import Optional
from fastapi import Header
from starlette.exceptions import HTTPException as StarletteHTTPException

_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

def _is_valid(key: str) -> bool:
    return 1 <= len(key) <= 64 and all(c in _ALLOWED for c in key)

async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Optional[str]:
    if idempotency_key is None:
        return None
    if not _is_valid(idempotency_key):
        # Make sure the Problem+JSON contains a 'code' field that tests look for.
        raise StarletteHTTPException(
            status_code=422,
            detail={
                "code": "IDEMPOTENCY_INVALID",
                "message": "Idempotency-Key must be 1–64 chars, [A-Za-z0-9_-] only.",
            },
        )
    return idempotency_key
