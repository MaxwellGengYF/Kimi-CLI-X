# Token limit threshold - if output exceeds this, export to a temp file
# Using 8000 as a conservative threshold to stay well below typical model limits
from pathlib import Path
import tempfile
OUTPUT_TOKEN_LIMIT = 1024
_temp_folder = Path.home() / '.kimi' / 'sessions'
_temp_idx = 0
_temp_set = dict()


def _estimate_tokens(text: str) -> int:
    """Rough estimation of token count (approximately 4 characters per token)."""
    return len(text) // 4


def _create_temp_file_name(ext:str = '.md') -> str:
    global _temp_idx
    id = _temp_idx
    _temp_idx += 1
    return str(_temp_folder / (str(id) + ext))


def _export_to_temp_file(key: Path | None, content: str, ext:str='.txt') -> tuple[str, bool]:
    global _temp_idx
    """Export content to a temporary file and return the file path."""
    id = _temp_idx
    new_id = True
    if key:
        v = _temp_set.get(key)
        if v is not None:
            id = v
            new_id = False
        else:
            # Add key to _temp_set with the new id
            _temp_set[key] = id
    if new_id:
        _temp_idx += 1
    name = str(_temp_folder / (str(id) + ext))
    # Append content if key exists, otherwise overwrite/create
    mode = 'a' if not new_id else 'w'
    with open(name, mode, encoding='utf-8') as f:
        f.write(content)
    return name, new_id


async def _export_to_temp_file_async(key: Path | None, content: str, ext:str='.txt') -> tuple[str, bool]:
    global _temp_idx
    """Async version: Export content to a temporary file and return the file path."""
    import anyio
    id = _temp_idx
    new_id = True
    if key:
        v = _temp_set.get(key)
        if v is not None:
            id = v
            new_id = False
        else:
            # Add key to _temp_set with the new id
            _temp_set[key] = id
    if new_id:
        _temp_idx += 1
    name = _temp_folder / (str(id) + ext)
    # Append content if key exists, otherwise overwrite/create
    mode = 'a' if not new_id else 'w'
    async with await anyio.open_file(name, mode, encoding='utf-8') as f:
        await f.write(content)
    return str(name), new_id


def _maybe_export_output(output: str, key: Path | None = None) -> str:
    """Check if output is too large and export to temp file if needed.

    Args:
        output: The output string to check.
        key: Optional Path to normalize and use in the output message.

    Returns:
        The output string, or a message indicating it was exported to a temp file.
    """
    if not output:
        return ''
    if _estimate_tokens(output) > OUTPUT_TOKEN_LIMIT:
        if key is not None:
            if type(key) is not Path:
                key = Path(key)
            key = key.resolve()
        temp_path, new_id = _export_to_temp_file(key, output)
        return f"[Output too large, {'exported' if new_id else 'added'} to file: {temp_path}]"
    return output


async def _maybe_export_output_async(output: str, key: Path | None = None) -> str:
    """Async version: Check if output is too large and export to temp file if needed.

    Args:
        output: The output string to check.
        key: Optional Path to normalize and use in the output message.

    Returns:
        The output string, or a message indicating it was exported to a temp file.
    """
    if not output:
        return ''
    if _estimate_tokens(output) > OUTPUT_TOKEN_LIMIT:
        if key is not None:
            if type(key) is not Path:
                key = Path(key)
            key = key.resolve()
        temp_path, new_id = await _export_to_temp_file_async(key, output)
        return f"[Output too large, {'exported' if new_id else 'added'} to file: {temp_path}]"
    return output
