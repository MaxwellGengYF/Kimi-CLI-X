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
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from kimix.server.bus import bus, BusEvent
from kimix.server.session_manager import session_manager
from kimix.summarize import summarize

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


# ── Request / Response Models ────────────────────────────────────


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="Session title")


class PromptPart(BaseModel):
    type: str = Field("text", description="Part type: text, tool, reasoning, etc.")
    text: str = Field("", description="Text content")


class PromptInput(BaseModel):
    parts: List[PromptPart] = Field(default_factory=list, description="Message parts")
    agent: Optional[str] = Field(None, description="Agent name to use")
    model: Optional[str] = Field(None, description="Model name to use")


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="New session title")


class FixSessionRequest(BaseModel):
    command: str = Field(..., description="Command to run and fix")
    extra_prompt: Optional[str] = Field(None, description="Extra prompt context")
    skip_success: bool = Field(True, description="Skip if no error on first run")
    keycode: List[str] = Field(default_factory=lambda: ["error"], description="Error keywords to look for")
    max_loop: int = Field(4, description="Maximum fix attempts")


# ── OpenAPI Response Models ──────────────────────────────────────


class HealthResponse(BaseModel):
    healthy: bool = Field(..., description="Server health status")
    version: str = Field(..., description="API version")


class SessionResponse(BaseModel):
    id: str = Field(..., description="Session UUID")
    title: Optional[str] = Field(None, description="Session title")
    createdAt: float = Field(..., description="Creation timestamp (unix)")
    updatedAt: float = Field(..., description="Last update timestamp (unix)")
    parentID: Optional[str] = Field(None, description="Parent session ID")


class MessagePartResponse(BaseModel):
    id: str = Field(..., description="Part UUID")
    type: str = Field(..., description="Part type: text | tool | reasoning | step-start | step-finish")
    text: Optional[str] = Field(None, description="Text content")
    tool: Optional[str] = Field(None, description="Tool name (for tool parts)")
    state: Optional[Dict[str, Any]] = Field(None, description="Tool state or step metadata")
    sessionID: str = Field(..., description="Session ID")
    messageID: str = Field(..., description="Message ID")
    createdAt: float = Field(..., description="Creation timestamp")


class MessageInfoResponse(BaseModel):
    id: str = Field(..., description="Message UUID")
    role: str = Field(..., description="Message role: user | assistant | system")
    sessionID: str = Field(..., description="Session ID")
    agent: str = Field(..., description="Agent name")
    createdAt: float = Field(..., description="Creation timestamp")


class MessageResponse(BaseModel):
    info: MessageInfoResponse = Field(..., description="Message metadata")
    parts: List[MessagePartResponse] = Field(default_factory=list, description="Message parts")


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

    @app.get(
        "/event",
        tags=["Events"],
        summary="SSE event stream",
        description="Server-Sent Events stream for real-time session updates, tool calls, and messages.",
        response_class=EventSourceResponse,
    )
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
                        event = await asyncio.wait_for(q.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            break
                        # Heartbeat
                        yield {
                            "data": json.dumps({
                                "type": "server.heartbeat",
                                "properties": {},
                            }),
                        }
                        continue
                    except asyncio.CancelledError:
                        break
                    if event is None:
                        break
                    yield {"data": event.to_json()}
            finally:
                bus.remove_async_queue(q)
                logger.info("SSE client disconnected")

        return EventSourceResponse(_generate())

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
        response_model=bool,
        tags=["Session"],
        summary="Delete session",
        description="Delete a session and close its underlying SDK session.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def delete_session(sessionID: str) -> bool:
        ok = await session_manager.delete_session(sessionID)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        return True

    @app.patch(
        "/session/{sessionID}",
        response_model=SessionResponse,
        tags=["Session"],
        summary="Update session",
        description="Update session metadata (e.g. title).",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
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

    @app.get(
        "/session/{sessionID}/message",
        response_model=List[MessageResponse],
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

    @app.post(
        "/session/{sessionID}/message",
        response_model=MessageResponse,
        tags=["Message"],
        summary="Send message (sync)",
        description="Send a prompt to the session and wait for the full assistant response. Blocks until completion.",
        responses={
            404: {"model": ErrorResponse, "description": "Session not found"},
            400: {"model": ErrorResponse, "description": "Invalid input"},
            500: {"model": ErrorResponse, "description": "Internal server error"},
        },
    )
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

    @app.post(
        "/session/{sessionID}/prompt_async",
        status_code=204,
        tags=["Message"],
        summary="Send message (async)",
        description="Send a prompt fire-and-forget style. Response events are streamed via SSE.",
        responses={
            404: {"model": ErrorResponse, "description": "Session not found"},
            400: {"model": ErrorResponse, "description": "Invalid input"},
        },
    )
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

    @app.post(
        "/session/{sessionID}/abort",
        response_model=bool,
        tags=["Session"],
        summary="Abort session",
        description="Abort the current running prompt in a session.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def abort_session(sessionID: str) -> bool:
        try:
            return session_manager.abort_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.post(
        "/session/{sessionID}/clear",
        response_model=bool,
        tags=["Session"],
        summary="Clear session",
        description="Clear the session history and reset its state.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def clear_session(sessionID: str) -> bool:
        try:
            return await session_manager.clear_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    @app.post(
        "/session/{sessionID}/summarize",
        response_model=bool,
        tags=["Session"],
        summary="Summarize session",
        description="Summarize and compact the session context.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def summarize_session(sessionID: str) -> bool:
        try:
            sdk_session = session_manager.get_sdk_session(sessionID)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        if sdk_session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")
        await summarize(session=sdk_session)
        return True

    @app.post(
        "/session/{sessionID}/fix",
        response_model=bool,
        tags=["Session"],
        summary="Fix error in session",
        description="Run a command and auto-fix errors using the session.",
        responses={404: {"model": ErrorResponse, "description": "Session not found"}},
    )
    async def fix_session_endpoint(sessionID: str, body: FixSessionRequest) -> bool:
        try:
            return await session_manager.fix_session(
                sessionID,
                command=body.command,
                extra_prompt=body.extra_prompt,
                skip_success=body.skip_success,
                keycode=tuple(body.keycode),
                max_loop=body.max_loop,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {sessionID}")

    return app
