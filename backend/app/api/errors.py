from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA = "application/problem+json"

def problem(status: int, code: str | None, title: str, detail: str):
    body = {"status": status, "title": title, "detail": detail}
    if code:
        body["code"] = code
    return body

async def on_validation_error(request: Request, exc):
    # Include code so tests can assert it
    return JSONResponse(
        problem(422, "VALIDATION_ERROR", "Validation failed", "Request body/params failed validation."),
        status_code=422,
        media_type=PROBLEM_MEDIA,
    )

async def on_http_exception(request: Request, exc: StarletteHTTPException):
    # If the raiser passed {"code": "...", "message": "..."} as detail, honor that
    code = None
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        detail = detail.get("message", str(detail))
    return JSONResponse(
        problem(exc.status_code, code or "ERROR", "Error", detail if isinstance(detail, str) else str(detail)),
        status_code=exc.status_code,
        media_type=PROBLEM_MEDIA,
    )

async def on_unhandled_exception(request: Request, exc):
    return JSONResponse(
        problem(500, "INTERNAL_ERROR", "Unexpected error", "Please try again."),
        status_code=500,
        media_type=PROBLEM_MEDIA,
    )
