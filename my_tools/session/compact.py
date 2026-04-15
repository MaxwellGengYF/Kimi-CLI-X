import anyio
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from pathlib import Path

DEFAULT_STORAGE_DIR = Path.home() / ".kimi/sessions/kv_store"


def _ensure_storage_dir():
    """Ensure the storage directory exists."""
    DEFAULT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_key(key: str) -> str:
    """Sanitize key to be safe for use as a filename.
    
    Uses base64 encoding to handle any characters that might be illegal in paths.
    """
    import base64
    # Encode the key to bytes, then to base64 (URL-safe to avoid / and +)
    encoded = base64.urlsafe_b64encode(key.encode('utf-8')).decode('ascii')
    # Remove padding '=' for cleaner filenames
    return encoded.rstrip('=')


def decode_key(safe_key: str) -> str:
    """Decode a sanitized key back to the original key.
    
    Reverses the _sanitize_key operation by adding padding and decoding base64.
    """
    import base64
    # Add back the padding '=' to make length a multiple of 4
    padding_needed = 4 - (len(safe_key) % 4)
    if padding_needed != 4:
        safe_key += '=' * padding_needed
    # Decode from base64 URL-safe, then to string
    decoded = base64.urlsafe_b64decode(safe_key.encode('ascii')).decode('utf-8')
    return decoded


def _get_key_path(key: str) -> Path:
    """Get the file path for a given key."""
    safe_key = _sanitize_key(key)
    return DEFAULT_STORAGE_DIR / f"{safe_key}.txt"


class StoreSessionParam(BaseModel):
    key: str = Field(
        default=None,
        description="Key to store data under."
    )
    value: str = Field(
        default=None,
        description="Data to store."
    )


class StoreSession(CallableTool2):
    name: str = "StoreSession"
    description: str = "Store session data."
    params: type[StoreSessionParam] = StoreSessionParam

    async def __call__(self, params: StoreSessionParam) -> ToolReturnValue:
        try:
            key = params.key if params.key else 'default'
            _ensure_storage_dir()
            file_path = _get_key_path(key)
            async with await anyio.open_file(file_path, 'w', encoding='utf-8') as f:
                await f.write(params.value)

            return ToolOk(output='')
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to save session",
            )


class LoadSessionParam(BaseModel):
    key: str = Field(
        default=None,
        description="Key to load data from."
    )


class LoadSession(CallableTool2):
    name: str = "LoadSession"
    description: str = "Load session data."
    params: type[LoadSessionParam] = LoadSessionParam

    @staticmethod
    def load(key=None):
        key = key if key else 'default'
        file_path = _get_key_path(key)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
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
                    message=f"Key '{key}' not found.",
                    brief="Key not found",
                )
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to load session",
            )


class LsSessionParam(BaseModel):
    pass


class LsSession(CallableTool2):
    name: str = "LsSession"
    description: str = "List session keys."
    params: type[LsSessionParam] = LsSessionParam

    async def __call__(self, params: LsSessionParam) -> ToolReturnValue:
        try:
            _ensure_storage_dir()
            if not DEFAULT_STORAGE_DIR.exists():
                return ToolOk(output="No sessions stored.")

            txt_files = list(DEFAULT_STORAGE_DIR.glob("*.txt"))
            if not txt_files:
                return ToolOk(output="No sessions stored.")

            decoded_keys = []
            for file_path in sorted(txt_files):
                safe_key = file_path.stem  # base name without extension
                try:
                    original_key = decode_key(safe_key)
                    decoded_keys.append(original_key)
                except Exception:
                    decoded_keys.append(f"[invalid: {safe_key}]")

            output = "\n".join(decoded_keys)
            return ToolOk(output=output)
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to list sessions",
            )
