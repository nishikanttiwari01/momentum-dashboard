from __future__ import annotations
import time
import logging
from typing import Callable, Awaitable
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("request")

class RequestLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method")
        path = scope.get("path")
        start = time.perf_counter()

        async def _send(message):
            if message["type"] == "http.response.start":
                status = message.get("status", 0)
                dur_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "req",
                    extra={
                        "method": method,
                        "path": path,
                        "status": status,
                        "duration_ms": round(dur_ms, 2),
                    },
                )
            await send(message)

        await self.app(scope, receive, _send)
