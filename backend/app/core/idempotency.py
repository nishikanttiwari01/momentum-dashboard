# backend/app/core/idempotency.py
from typing import Optional
from fastapi import Header
from fastapi.exceptions import RequestValidationError

ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

def _is_valid(key: str) -> bool:
    return 1 <= len(key) <= 64 and all(c in ALLOWED for c in key)

async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
) -> Optional[str]:
    if idempotency_key is None:
        return None
    if not _is_valid(idempotency_key):
        raise RequestValidationError([{
            "loc": ("header", "Idempotency-Key"),
            "msg": "Invalid Idempotency Key: must be 1–64 chars, [A-Za-z0-9_-] only.",
            "type": "value_error.idempotency_key",
        }])
    return idempotency_key
