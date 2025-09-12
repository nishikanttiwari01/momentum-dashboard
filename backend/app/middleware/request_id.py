from __future__ import annotations
import uuid
from starlette.types import ASGIApp, Receive, Scope, Send

class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # get or generate
        headers = dict((k.decode().lower(), v.decode()) for k, v in scope["headers"])
        req_id = headers.get(self.header_name.lower(), str(uuid.uuid4()))

        async def _send(message):
            if message["type"] == "http.response.start":
                # add/echo header
                headers = message.setdefault("headers", [])
                headers.append((self.header_name.encode(), req_id.encode()))
            await send(message)

        await self.app(scope, receive, _send)
