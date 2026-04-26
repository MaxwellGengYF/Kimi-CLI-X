# -*- coding: utf-8 -*-
"""Kimix opencode-style HTTP server (FastAPI + SSE).

Provides REST API endpoints compatible with the opencode serve interface.

Routes:
    GET  /global/health              — Health check
    GET  /event                      — SSE event stream
    POST /session                    — Create session
    GET  /session                    — List sessions
    GET  /session/status             — Get all session statuses
    GET  /session/{sessionID}        — Get session info
    DELETE /session/{sessionID}      — Delete session
    GET  /session/{sessionID}/message — Get messages
    POST /session/{sessionID}/message — Send message (sync wait)
    POST /session/{sessionID}/prompt_async — Send message (fire-and-forget)
    POST /session/{sessionID}/abort  — Abort session
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from kimix.server.bus import bus, BusEvent
from kimix.server.session_manager import session_manager

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


# ── Request / Response Models ────────────────────────────────────


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


class PromptPart(BaseModel):
    type: str = "text"
    text: str = ""


class PromptInput(BaseModel):
    parts: List[PromptPart] = []
    agent: Optional[str] = None
    model: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None


# ── Application Factory ─────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="kimix",
        version=VERSION,
        description="Kimix opencode-style API server",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health ────────────────────────────────────────────────

    @app.get("/global/health")
    async def health() -> Dict[str, Any]:
        return {"healthy": True, "version": VERSION}

    # ── SSE Event Stream ─────────────────────────────────────

    @app.get("/event")
    async def event_stream(request: Request) -> EventSourceResponse:
        async def _generate():  # type: ignore[return]
            # Send initial connected event
            yield {
                "data": json.dumps({
                    "type": "server.connected",
                    "properties": {},
                }),
            }

            q = bus.create_async_queue()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        # Heartbeat
                        yield {
                            "data": json.dumps({
                                "type": "server.heartbeat",
                                "properties": {},
                            }),
                        }
                        continue
                    if event is None:
                        break
                    yield {"data": event.to_json()}
            finally:
                bus.remove_async_queue(q)
                logger.info("SSE client disconnected")

        return EventSourceResponse(_generate())

    # ── Session CRUD ─────────────────────────────────────────

    @app.post("/session")
    async def create_session(body: CreateSessionRequest) -> Dict[str, Any]:
        info = await session_manager.create_session(title=body.title)
        return info.to_dict()

    @app.get("/session")
    async def list_sessions() -> List[Dict[str, Any]]:
        return [s.to_dict() for s in session_manager.list_sessions()]

    @app.get("/session/status")
    async def session_status() -> Dict[str, Dict[str, Any]]:
        return session_manager.get_session_status()

    @app.get("/session/{sessionID}")
    async def get_session(sessionID: str) -> Dict[str, Any]:
        try:
            return session_manager.get_session(sessionID).to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.delete("/session/{sessionID}")
    async def delete_session(sessionID: str) -> bool:
        ok = await session_manager.delete_session(sessionID)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        return True

    @app.patch("/session/{sessionID}")
    async def update_session(sessionID: str, body: UpdateSessionRequest) -> Dict[str, Any]:
        try:
            info = session_manager.get_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        if body.title is not None:
            info.title = body.title
            info.updatedAt = time.time()
            bus.emit_type("session.updated", sessionID=sessionID, info=info.to_dict())
        return info.to_dict()

    # ── Messages ─────────────────────────────────────────────

    @app.get("/session/{sessionID}/message")
    async def get_messages(
        sessionID: str,
        limit: Optional[int] = Query(default=None),
    ) -> List[Dict[str, Any]]:
        try:
            return session_manager.get_messages(sessionID, limit=limit)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.post("/session/{sessionID}/message")
    async def send_message(sessionID: str, body: PromptInput) -> Dict[str, Any]:
        text_parts = [p.text for p in body.parts if p.type == "text" and p.text]
        text = "\n".join(text_parts)
        if not text:
            raise HTTPException(status_code=400, detail="No text content in parts")
        try:
            result = await session_manager.prompt(
                sessionID, text, agent=body.agent
            )
            return result
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/session/{sessionID}/prompt_async", status_code=204)
    async def send_prompt_async(sessionID: str, body: PromptInput) -> None:
        text_parts = [p.text for p in body.parts if p.type == "text" and p.text]
        text = "\n".join(text_parts)
        if not text:
            raise HTTPException(status_code=400, detail="No text content in parts")
        try:
            await session_manager.prompt_async(
                sessionID, text, agent=body.agent
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.post("/session/{sessionID}/abort")
    async def abort_session(sessionID: str) -> bool:
        try:
            return session_manager.abort_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    return app
