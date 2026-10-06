# pyright: reportAny=false
# ASGI Message is an upstream dict[str, Any]; the server contract fixes body to bytes.
from typing import Final

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BYTES: Final = 128_000


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app: ASGIApp = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        chunks = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk: bytes = message.get("body", b"")
            if len(chunks) + len(chunk) > MAX_REQUEST_BYTES:
                await JSONResponse({"error": "request_too_large"}, status_code=413)(
                    scope, receive, send
                )
                return
            chunks.extend(chunk)
            if not message.get("more_body", False):
                break
        consumed = False

        async def buffered_receive() -> Message:
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(chunks), "more_body": False}

        await self.app(scope, buffered_receive, send)
