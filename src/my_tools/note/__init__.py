"""Manage persistent notes for working memory."""

from pathlib import Path
from typing import Any, Literal

import anyio
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from kimi_cli.session import Session
from pydantic import BaseModel, Field

MAGIC_SPLIT_STR = '\n>>>>>>>>>>9fbf5c1387a34\n'


def read_file(path: Path | None) -> list[str]:
    if not (path is not None and path.exists()):
        return []
    text = path.read_text(encoding='utf-8', errors='replace')
    if text:
        lst: list[str] = text.split(MAGIC_SPLIT_STR)
        for i, v in enumerate(lst):
            lst[i] = v.strip()
        return lst
    return []


class Params(BaseModel):
    content: str = Field(
        description="Note content.",
    )


class Note(CallableTool2):
    name: str = "Note"
    description: str = 'Append a note to a file.'
    params: type[Params] = Params

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def __call__(self, params: Params) -> ToolReturnValue:
        path: Path | None = self._session.custom_data.get('note_writing_path')
        if path is None:
            return ToolError(
                output="",
                message="Note tool invalid",
                brief="invalid tool.",
            )
        try:
            previous_exists = path.exists()
            await anyio.to_thread.run_sync(lambda: path.parent.mkdir(parents=True, exist_ok=True))
            async with await anyio.open_file(path, 'a', encoding='utf-8') as f:
                if previous_exists:
                    await f.write(MAGIC_SPLIT_STR)
                await f.write(params.content)
            self._session.custom_data['note_called'] = True
            return ToolOk(output=f"Note appended to {path}")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to append note",
            )
