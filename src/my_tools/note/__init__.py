"""Manage persistent notes for working memory."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import anyio
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
import threading

WRITING_PATH = threading.local()
MAGIC_SPLIT_STR = '\n>>>>>>>>>>9fbf5c1387a34\n'


def set_writing_path(path: Path | None):
    setattr(WRITING_PATH, 'trigger', False)
    setattr(WRITING_PATH, 'value', path)


def is_note_called():
    return getattr(WRITING_PATH, 'trigger', False)


def get_writing_path() -> Path | None:
    path: Path | None = getattr(WRITING_PATH, 'value', None)
    return path


def read_file(path: Path | None) -> list[str]:
    if not (path is not None and path.exists()):
        return []
    text = path.read_text(encoding='utf-8', errors='replace')
    if text:
        return text.split(MAGIC_SPLIT_STR)
    return []


class Params(BaseModel):
    content: str = Field(
        description="Note content.",
    )


class Note(CallableTool2):
    name: str = "Note"
    description: str = 'append note to a file.'
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        path: Path | None = getattr(WRITING_PATH, 'value', None)
        if path is None:
            return ToolError(
                output="",
                message="Writing path is not set. Call set_writing_path first.",
                brief="No writing path configured",
            )
        try:
            setattr(WRITING_PATH, 'trigger', True)
            previous_exists = path.exists()
            await anyio.to_thread.run_sync(lambda: path.parent.mkdir(parents=True, exist_ok=True))
            async with await anyio.open_file(path, 'a', encoding='utf-8') as f:
                if previous_exists:
                    await f.write(MAGIC_SPLIT_STR)
                await f.write(params.content)
            return ToolOk(output=f"Note appended to {path}")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to append note",
            )
