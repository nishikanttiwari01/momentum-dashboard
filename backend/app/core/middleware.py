import time, uuid, logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)

class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        run_id = request.headers.get("X-Run-Id", "")
        endpoint = request.url.path

        # Make req_id available to downstream (e.g., response headers)
        request.state.req_id = req_id
        request.state.run_id = run_id

        try:
            response: Response = await call_next(request)
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.info(
                "request",
                extra={"req_id": req_id, "run_id": run_id, "endpoint": endpoint, "duration_ms": duration_ms},
            )
        # reflect req_id back to client
        response.headers["X-Request-ID"] = req_id
        return response
