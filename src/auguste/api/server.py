"""Local API used by the Houdini dialog/panel.

HTTP:
  GET  /health
  POST /sessions                          -> {"session_id"}
  POST /sessions/{sid}/messages {"text"}  -> NDJSON stream of agent events
  POST /sessions/{sid}/confirm {"id", "approved"}
  POST /sessions/{sid}/stop
WebSocket /sessions/{sid}/ws: send {"type": "message"|"confirm"|"stop", ...}, receive events.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from auguste.agent.loop import Confirm, Event
from auguste.agent.policy import Tier
from auguste.agent.providers.base import ToolCall



class Runner(Protocol):
    """loop.Agent (LiteLLM) or claude_code.ClaudeCodeAgent (subscription)."""

    def run(self, user_text: str) -> AsyncIterator[Event]: ...

    def stop(self) -> None: ...


AgentFactory = Callable[[Confirm], Runner]


@dataclass
class Session:
    agent: Runner = None  # type: ignore[assignment]
    pending: dict[str, asyncio.Future[bool]] = field(default_factory=dict)
    busy: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def confirm(self, call: ToolCall, tier: Tier) -> bool:
        future = asyncio.get_running_loop().create_future()
        self.pending[call.id] = future
        try:
            return await future
        finally:
            self.pending.pop(call.id, None)

    def answer(self, call_id: str, approved: bool) -> bool:
        future = self.pending.get(call_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True

    def stop(self) -> None:
        self.agent.stop()
        for future in list(self.pending.values()):
            if not future.done():
                future.set_result(False)

    async def events(self, text: str) -> AsyncIterator[Event]:
        async with self.busy:
            try:
                async for event in self.agent.run(text):
                    yield event
            finally:
                self.stop()  # releases waiting confirms if the client went away


def create_app(
    make_agent: AgentFactory,
    info: dict[str, Any] | None = None,
    lifespan: Any = None,
) -> Starlette:
    sessions: dict[str, Session] = {}

    def get(request: Request | WebSocket) -> Session | None:
        return sessions.get(request.path_params["sid"])

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, **(info or {})})

    async def new_session(request: Request) -> JSONResponse:
        session = Session()
        session.agent = make_agent(session.confirm)
        sid = uuid.uuid4().hex
        sessions[sid] = session
        return JSONResponse({"session_id": sid})

    async def message(request: Request) -> Any:
        session = get(request)
        if session is None:
            return JSONResponse({"error": "unknown session"}, status_code=404)
        if session.busy.locked():
            return JSONResponse({"error": "session is busy"}, status_code=409)
        text = (await request.json()).get("text", "")

        async def stream() -> AsyncIterator[str]:
            async for event in session.events(text):
                yield json.dumps(event.as_dict(), default=str) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    async def confirm(request: Request) -> JSONResponse:
        session = get(request)
        if session is None:
            return JSONResponse({"error": "unknown session"}, status_code=404)
        body = await request.json()
        ok = session.answer(str(body.get("id")), bool(body.get("approved")))
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    async def stop(request: Request) -> JSONResponse:
        session = get(request)
        if session is None:
            return JSONResponse({"error": "unknown session"}, status_code=404)
        session.stop()
        return JSONResponse({"ok": True})

    async def websocket(ws: WebSocket) -> None:
        session = get(ws)
        await ws.accept()
        if session is None:
            await ws.close(code=4404)
            return
        run: asyncio.Task[None] | None = None

        async def drive(text: str) -> None:
            async for event in session.events(text):
                await ws.send_json(event.as_dict())

        try:
            while True:
                msg = await ws.receive_json()
                kind = msg.get("type")
                if kind == "message":
                    if run and not run.done():
                        await ws.send_json({"type": "error", "message": "session is busy"})
                    else:
                        run = asyncio.create_task(drive(msg.get("text", "")))
                elif kind == "confirm":
                    session.answer(str(msg.get("id")), bool(msg.get("approved")))
                elif kind == "stop":
                    session.stop()
        except WebSocketDisconnect:
            session.stop()
            if run:
                run.cancel()

    return Starlette(
        routes=[
            Route("/health", health),
            Route("/sessions", new_session, methods=["POST"]),
            Route("/sessions/{sid}/messages", message, methods=["POST"]),
            Route("/sessions/{sid}/confirm", confirm, methods=["POST"]),
            Route("/sessions/{sid}/stop", stop, methods=["POST"]),
            WebSocketRoute("/sessions/{sid}/ws", websocket),
        ],
        lifespan=lifespan,
    )
