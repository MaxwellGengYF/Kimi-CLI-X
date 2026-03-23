# Token limit threshold - if output exceeds this, export to a temp file
# Using 8000 as a conservative threshold to stay well below typical model limits
from pathlib import Path
import tempfile
OUTPUT_TOKEN_LIMIT = 4096
_temp_folder = Path.home() / '.kimi' / 'sessions'
_temp_idx = 0


def _estimate_tokens(text: str) -> int:
    """Rough estimation of token count (approximately 4 characters per token)."""
    return len(text) // 4


def _export_to_temp_file(content: str) -> str:
    global _temp_idx
    """Export content to a temporary file and return the file path."""
    name = str(_temp_folder / str(_temp_idx))
    with open(name, 'w', encoding='utf-8') as f:
        f.write(content)
    _temp_idx += 1
    return name


def _maybe_export_output(output: str) -> str:
    """Check if output is too large and export to temp file if needed."""
    if _estimate_tokens(output) > OUTPUT_TOKEN_LIMIT:
        temp_path = _export_to_temp_file(output)
        return f"[Output too large, exported to temp file: {temp_path}]"
    return output
