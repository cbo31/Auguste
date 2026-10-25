"""Short-lived localhost HTTP endpoint that the permission MCP server posts to.
The path carries a random token so other local processes can't answer approvals."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class CallbackServer:
    def __init__(self, handler: Handler):
        self.handler = handler
        self.token = secrets.token_urlsafe(16)
        self._server: Any = None
        self._task: asyncio.Task[None] | None = None

    async def _handle(self, request: Request) -> JSONResponse:
        return JSONResponse(await self.handler(await request.json()))

    async def __aenter__(self) -> str:
        import uvicorn

        app = Starlette(routes=[Route(f"/{self.token}", self._handle, methods=["POST"])])
        self._server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off", timeout_graceful_shutdown=2))
        self._server.install_signal_handlers = lambda: None  # runs inside another server's loop
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            if self._task.done():
                await self._task  # surfaces the startup error
            await asyncio.sleep(0.01)
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/{self.token}"

    async def __aexit__(self, *exc: object) -> None:
        self._server.should_exit = True
        await self._task
