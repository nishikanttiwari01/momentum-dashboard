from typing import Any, List, Optional, Dict
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import uuid

class ProblemCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    IDEMPOTENCY_INVALID = "IDEMPOTENCY_INVALID"

def problem_response(
    status: int,
    title: str,
    detail: Optional[str] = None,
    code: Optional[str] = None,
    instance: Optional[str] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
):
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "instance": instance or f"urn:problem:{uuid.uuid4()}",
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json")

# Exception handlers
async def on_validation_error(request: Request, exc: RequestValidationError):
    errs = []
    for e in exc.errors():
        errs.append({"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")})
    return problem_response(
        status=422,
        title="Unprocessable Entity",
        detail="Input failed validation",
        code=ProblemCode.VALIDATION_ERROR,
        errors=errs,
    )

async def on_http_exception(request: Request, exc: StarletteHTTPException):
    # map to Problem
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(status=exc.status_code, title="HTTP Error", detail=detail)

async def on_unhandled_exception(request: Request, exc: Exception):
    return problem_response(status=500, title="Internal Server Error", code=ProblemCode.INTERNAL_ERROR)
