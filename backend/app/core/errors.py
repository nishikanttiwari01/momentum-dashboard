from fastapi import Request
from fastapi.responses import JSONResponse

def problem(status: int, code: str, title: str, detail: str):
    return {"status": status, "code": code, "title": title, "detail": detail}

async def on_validation_error(request: Request, exc):
    return JSONResponse(problem(422, "VALIDATION_ERROR", "Validation failed", str(exc)), status_code=422)

async def on_unhandled_exception(request: Request, exc):
    return JSONResponse(problem(500, "INTERNAL_ERROR", "Unexpected error", "Please try again."), status_code=500)
