# -*- coding: utf-8 -*-
"""Kimix opencode-style HTTP server (FastAPI + SSE).

Provides REST API endpoints fully compatible with the opencode serve interface.

Routes (opencode-standard):
    GET  /global/health                    — Health check
    GET  /event                            — SSE event stream (global)
    POST /session                          — Create session
    GET  /session                          — List sessions
    GET  /session/status                   — Get all session statuses
    GET  /session/{sessionID}              — Get session info
    DELETE /session/{sessionID}            — Delete session
    GET  /session/{sessionID}/message      — Get messages
    POST /session/{sessionID}/prompt_async — Send message (fire-and-forget, 204)
    POST /session/{sessionID}/abort        — Abort session
    POST /session/{sessionID}/permissions/{permissionID} — Grant permission
    GET  /session/{sessionID}/clear        — Clear session
    GET  /session/{sessionID}/context      — Get session context
    GET  /session/{sessionID}/compact      — Compact session
    GET  /session/{sessionID}/export       — Export session
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from kimix.server.bus import bus, BusEvent
from kimix.server.session_manager import session_manager

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


# ── Request / Response Models ────────────────────────────────────


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="Session title")


class PromptPart(BaseModel):
    type: str = Field("text", description="Part type: text")
    text: str = Field("", description="Text content")


class PromptInput(BaseModel):
    parts: List[PromptPart] = Field(default_factory=list, description="Message parts")
    agent: Optional[str] = Field(None, description="Agent name to use")
    model: Optional[str] = Field(None, description="Model name to use")


# ── OpenAPI Response Models ──────────────────────────────────────


class HealthResponse(BaseModel):
    healthy: bool = Field(..., description="Server health status")
    version: str = Field(..., description="API version")


class SessionResponse(BaseModel):
    id: str = Field(..., description="Session ID (ses_ prefix)")
    title: Optional[str] = Field(None, description="Session title")
    createdAt: float = Field(..., description="Creation timestamp (unix)")
    updatedAt: float = Field(..., description="Last update timestamp (unix)")
    parentID: Optional[str] = Field(None, description="Parent session ID")


class SessionStatusResponse(BaseModel):
    type: str = Field(..., description="Status: idle | busy | error")
    time: float = Field(..., description="Status timestamp (unix)")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error detail message")


# ── Application Factory ─────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kimix API",
        version=VERSION,
        description="Kimix opencode-style REST API server. Use /docs for interactive Swagger UI.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Server shutting down, waking up SSE streams")
        for q in bus.get_all_queues():
            try:
                q.put_nowait(None)
            except Exception:
                pass

    # ── Health ────────────────────────────────────────────────

    @app.get(
        "/global/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check",
        description="Returns server health status and API version.",
    )
    async def health() -> Dict[str, Any]:
        return {"healthy": True, "version": VERSION}

    # ── SSE Event Stream ─────────────────────────────────────
    #
    # OpenCode protocol: NO SSE `event:` field is used.
    # All events are plain `data: {json}\n\n` lines.
    # We use a raw StreamingResponse to have full control over
    # the wire format instead of sse-starlette which adds event: fields.

    @app.get(
        "/event",
        tags=["Events"],
        summary="SSE event stream",
        description=(
            "Server-Sent Events stream for real-time session updates. "
            "Global endpoint — pushes events for ALL sessions. "
            "Client should filter by sessionID in properties."
        ),
    )
    async def event_stream(request: Request) -> StreamingResponse:
        async def _generate():  # type: ignore[return]
            # Send initial connected event
            connected = json.dumps(
                {"type": "server.connected", "properties": {}},
                ensure_ascii=False,
            )
            yield f"data: {connected}\n\n"

            q = bus.create_async_queue()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            break
                        # SSE comment heartbeat (no event: field, just a comment)
                        yield ": heartbeat\n\n"
                        continue
                    except asyncio.CancelledError:
                        break
                    if event is None:
                        break
                    yield f"data: {event.to_json()}\n\n"
            finally:
                bus.remove_async_queue(q)
                logger.info("SSE client disconnected")

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Session CRUD ─────────────────────────────────────────

    @app.post(
        "/session",
        response_model=SessionResponse,
        tags=["Session"],
        summary="Create session",
        description="Create a new chat session. Returns the session metadata.",
        status_code=200,
    )
    async def create_session(body: CreateSessionRequest) -> Dict[str, Any]:
        info = await session_manager.create_session(title=body.title)
        return info.to_dict()

    @app.get(
        "/session",
        response_model=List[SessionResponse],
        tags=["Session"],
        summary="List sessions",
        description="List all active sessions, sorted by most recently updated.",
    )
    async def list_sessions() -> List[Dict[str, Any]]:
        return [s.to_dict() for s in session_manager.list_sessions()]

    @app.get(
        "/session/status",
        response_model=Dict[str, SessionStatusResponse],
        tags=["Session"],
        summary="Get all session statuses",
        description="Returns a map of session ID to current status (idle/busy/error).",
    )
    async def session_status() -> Dict[str, Dict[str, Any]]:
        return session_manager.get_session_status()

    @app.get(
        "/session/{sessionID}",
        response_model=SessionResponse,
        tags=["Session"],
        summary="Get session",
        description="Get metadata for a specific session by ID.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def get_session(sessionID: str) -> Dict[str, Any]:
        try:
            return session_manager.get_session(sessionID).to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.delete(
        "/session/{sessionID}",
        tags=["Session"],
        summary="Delete session",
        description="Delete a session and close its underlying SDK session.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
        status_code=200,
    )
    async def delete_session(sessionID: str) -> Response:
        ok = await session_manager.delete_session(sessionID)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        return Response(status_code=200)

    # ── Messages ─────────────────────────────────────────────

    @app.get(
        "/session/{sessionID}/message",
        tags=["Message"],
        summary="Get messages",
        description="Get messages for a session. Optionally limit the number of most recent messages.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def get_messages(
        sessionID: str,
        limit: Optional[int] = Query(default=None, description="Maximum number of messages to return"),
    ) -> List[Dict[str, Any]]:
        try:
            return session_manager.get_messages(sessionID, limit=limit)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    # ── Prompt Async (fire-and-forget) ───────────────────────

    @app.post(
        "/session/{sessionID}/prompt_async",
        status_code=204,
        tags=["Message"],
        summary="Send message (async)",
        description="Send a prompt fire-and-forget style. Returns 204 immediately. Response events are streamed via SSE /event.",
        responses={
            404: {"model": ErrorResponse, "description": "Session not found"},
            400: {"model": ErrorResponse, "description": "Invalid input"},
        },
    )
    async def send_prompt_async(sessionID: str, body: PromptInput) -> Response:
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
        return Response(status_code=204)

    # ── Abort ────────────────────────────────────────────────

    @app.post(
        "/session/{sessionID}/abort",
        tags=["Session"],
        summary="Abort session",
        description="Abort the current running prompt in a session.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
        status_code=200,
    )
    async def abort_session(sessionID: str) -> Response:
        try:
            session_manager.abort_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        return Response(status_code=200)

    # ── Permissions ──────────────────────────────────────────

    @app.post(
        "/session/{sessionID}/permissions/{permissionID}",
        tags=["Session"],
        summary="Grant permission",
        description="Grant a pending permission request.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
        status_code=200,
    )
    async def grant_permission(sessionID: str, permissionID: str) -> Response:
        # Permission handling — acknowledge for now
        logger.info("Permission granted: session=%s, permission=%s", sessionID, permissionID)
        return Response(status_code=200)

    # ── Options ──────────────────────────────────────────────

    @app.get(
        "/session/{sessionID}/clear",
        tags=["Options"],
        summary="Clear session",
        description="Clear a specific session and return a confirmation.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def clear_session(sessionID: str) -> Dict[str, Any]:
        try:
            await session_manager.clear_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        return {"cleared": 1, "sessionID": sessionID}


    @app.get(
        "/session/{sessionID}/context",
        tags=["Options"],
        summary="Get session context",
        description="Return context for a specific session.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def get_session_context(sessionID: str) -> Dict[str, Any]:
        try:
            return session_manager.get_session_context(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.get(
        "/session/{sessionID}/compact",
        tags=["Options"],
        summary="Compact session",
        description="Compact a specific session by trimming message history.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def compact_session(
        sessionID: str,
        keep: Optional[int] = Query(default=10, ge=0, description="Number of recent messages to keep"),
    ) -> Dict[str, Any]:
        try:
            await session_manager.compact_session(sessionID, keep=keep)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        return {"compacted": 1, "sessionID": sessionID, "keep": keep}

    @app.get(
        "/session/{sessionID}/export",
        tags=["Options"],
        summary="Export session",
        description="Export a specific session to a file.",
        responses={
            404: {"model": ErrorResponse, "description": "Session not found"},
            400: {"model": ErrorResponse, "description": "Invalid input"},
        },
    )
    async def export_session(
        sessionID: str,
        output_path: Optional[str] = Query(default=None, description="Output file path"),
    ) -> Dict[str, Any]:
        try:
            output, count = await session_manager.export_session(sessionID, output_path=output_path)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"output": output, "count": count, "sessionID": sessionID}

    return app
