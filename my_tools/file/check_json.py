"""JSON file validator tool."""
import json


def check_json(file_content: str) -> str | None:
    """Validate the format of JSON content.
    
    Args:
        file_content: The JSON content to validate.
        
    Returns:
        None if the JSON content is valid, error message string otherwise.
    """
    try:
        json.loads(file_content)
        return None
    
    except json.JSONDecodeError as exc:
        return f"JSON decode error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except Exception as exc:
        return f"Failed to validate JSON content: {str(exc)}"
