"""JSON file validator tool."""
import json


def check_json(file_path: str) -> str | None:
    """Validate the format of a JSON file.
    
    Args:
        file_path: Path to the JSON file to validate.
        
    Returns:
        None if the JSON file is valid, error message string otherwise.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        return None
    
    except json.JSONDecodeError as exc:
        return f"JSON decode error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except Exception as exc:
        return f"Failed to validate JSON file: {str(exc)}"


"""XML file validator tool."""
import xml.etree.ElementTree as ET


def check_xml(file_path: str) -> str | None:
    """Validate the format of an XML file.
    
    Args:
        file_path: Path to the XML file to validate.
        
    Returns:
        None if the XML file is valid, error message string otherwise.
    """
    try:
        ET.parse(file_path)
        return None
    
    except ET.ParseError as exc:
        return f"XML parse error: {str(exc)}"
    except Exception as exc:
        return f"Failed to validate XML file: {str(exc)}"
