import threading
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
import dbm
from pathlib import Path
DEFAULT_DB_PATH = Path.home() / ".kimi/sessions/kv_store.db"


class SaveSessionParam(BaseModel):
    value: str = Field(
        default=None,
        description="The context",
    )


_current_key = threading.local()


class SaveSession(CallableTool2):
    name: str = "SaveSession"
    description: str = "Save session context."
    params: type[SaveSessionParam] = SaveSessionParam

    async def __call__(self, params: SaveSessionParam) -> ToolReturnValue:
        try:
            key = getattr(_current_key, 'key', 'default')
            with dbm.open(DEFAULT_DB_PATH, 'c') as db:
                db[key.encode('utf-8')] = params.value.encode('utf-8')

            return ToolOk(output=f"Done")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to save session",
            )


class LoadSessionParam(BaseModel):
    key: str = Field(
        default=None,
        description="The context key to load",
    )


class LoadSession(CallableTool2):
    name: str = "LoadSession"
    description: str = "Load session context."
    params: type[LoadSessionParam] = LoadSessionParam
    @staticmethod
    def load(key=None):
        if key is None:
            key = getattr(_current_key, 'key', 'default')
        with dbm.open(DEFAULT_DB_PATH, 'c') as db:
            key_bytes = key.encode('utf-8')
            if key_bytes in db:
                return db[key_bytes].decode('utf-8')
        return None
    async def __call__(self, params: LoadSessionParam) -> ToolReturnValue:
        try:
            key = params.key
            value = LoadSession.load(key)
            if value is not None:
                return ToolOk(output=value)
            else:
                return ToolError(
                    output="",
                    message=f"Key '{key}' not found in database.",
                    brief="Key not found",
                )
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to load session",
            )
