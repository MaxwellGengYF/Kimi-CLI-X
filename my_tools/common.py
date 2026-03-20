# Token limit threshold - if output exceeds this, export to a temp file
# Using 8000 as a conservative threshold to stay well below typical model limits
import tempfile
OUTPUT_TOKEN_LIMIT = 1024


def _estimate_tokens(text: str) -> int:
    """Rough estimation of token count (approximately 4 characters per token)."""
    return len(text) // 4


def _export_to_temp_file(content: str) -> str:
    """Export content to a temporary file and return the file path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(content)
        return f.name


def _maybe_export_output(output: str) -> str:
    """Check if output is too large and export to temp file if needed."""
    if _estimate_tokens(output) > OUTPUT_TOKEN_LIMIT:
        temp_path = _export_to_temp_file(output)
        return f"[Output too large, exported to temp file: {temp_path}]"
    return output
