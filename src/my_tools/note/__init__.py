"""Manage persistent notes for working memory."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import anyio
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

# Default notes storage path
DEFAULT_NOTES_PATH: Path = Path.home() / ".kimi" / "notes.json"


class Params(BaseModel):
    """Parameters for Note tool."""

    action: Literal["add", "get", "list", "delete", "clear"] = Field(
        description="Action to perform: 'add', 'get', 'list', 'delete', 'clear'."
    )
    key: str | None = Field(
        default=None,
        description="Note key/title. Required for add, get, delete.",
    )
    content: str | None = Field(
        default=None,
        description="Note content. Required for add.",
    )
    category: str | None = Field(
        default=None,
        description="Optional category for organizing notes.",
    )


class Note(CallableTool2):
    """Manage persistent notes."""

    name: str = "Note"
    description: str = (
        "Manage persistent notes: add, get, list, delete, or clear notes."
    )
    params: type[Params] = Params

    def _load_notes(self) -> dict[str, Any]:
        if not DEFAULT_NOTES_PATH.exists():
            return {}
        try:
            with open(DEFAULT_NOTES_PATH, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
                return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_notes(self, notes: dict[str, Any]) -> None:
        DEFAULT_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEFAULT_NOTES_PATH, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)

    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            notes = await anyio.to_thread.run_sync(self._load_notes)

            if params.action == "add":
                if not params.key:
                    return ToolError(
                        message="Key is required for add action.",
                        output="",
                        brief="Missing key",
                    )
                note_data: dict[str, Any] = {
                    "content": params.content or "",
                    "category": params.category or "general",
                    "created_at": datetime.now().isoformat(),
                }
                notes[params.key] = note_data
                await anyio.to_thread.run_sync(self._save_notes, notes)
                return ToolOk(output=f"Note '{params.key}' added.")

            if params.action == "get":
                if not params.key:
                    return ToolError(
                        message="Key is required for get action.",
                        output="",
                        brief="Missing key",
                    )
                if params.key not in notes:
                    return ToolError(
                        message=f"Note '{params.key}' not found.",
                        output="",
                        brief="Note not found",
                    )
                note = notes[params.key]
                output = (
                    f"Key: {params.key}\n"
                    f"Content: {note.get('content', '')}\n"
                    f"Category: {note.get('category', 'general')}"
                )
                return ToolOk(output=output)

            if params.action == "list":
                if not notes:
                    return ToolOk(output="No notes found.")
                lines: list[str] = []
                for k, v in notes.items():
                    cat = v.get("category", "general")
                    content_preview = v.get("content", "")[:50]
                    lines.append(f"- {k} [{cat}]: {content_preview}")
                return ToolOk(output="\n".join(lines))

            if params.action == "delete":
                if not params.key:
                    return ToolError(
                        message="Key is required for delete action.",
                        output="",
                        brief="Missing key",
                    )
                if params.key not in notes:
                    return ToolError(
                        message=f"Note '{params.key}' not found.",
                        output="",
                        brief="Note not found",
                    )
                del notes[params.key]
                await anyio.to_thread.run_sync(self._save_notes, notes)
                return ToolOk(output=f"Note '{params.key}' deleted.")

            if params.action == "clear":
                await anyio.to_thread.run_sync(self._save_notes, {})
                return ToolOk(output="All notes cleared.")

            return ToolError(
                message=f"Unknown action: {params.action}",
                output="",
                brief="Invalid action",
            )

        except Exception as e:
            return ToolError(
                message=str(e),
                output="",
                brief="Note operation failed",
            )
