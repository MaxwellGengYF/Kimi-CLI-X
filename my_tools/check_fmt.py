"""JSON file validator tool."""
import xml.etree.ElementTree as ET
import json
from enum import Enum


def check_json(file_path: str, json_callback = None) -> str | None:
    """Validate the format of a JSON file.

    Args:
        file_path: Path to the JSON file to validate.

    Returns:
        None if the JSON file is valid, error message string otherwise.
    """
    try:
        js = None
        with open(file_path, 'r', encoding='utf-8') as f:
            js = json.load(f)
        if json_callback:
            json_callback(js)
        return None

    except json.JSONDecodeError as exc:
        return f"JSON decode error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except Exception as exc:
        return f"Failed to validate JSON file: {str(exc)}"


"""XML file validator tool."""


def check_xml(file_path: str, xml_callback = None) -> str | None:
    """Validate the format of an XML file.

    Args:
        file_path: Path to the XML file to validate.

    Returns:
        None if the XML file is valid, error message string otherwise.
    """
    try:
        tree = ET.parse(file_path)
        xml_callback(tree)
        return None

    except ET.ParseError as exc:
        return f"XML parse error: {str(exc)}"
    except Exception as exc:
        return f"Failed to validate XML file: {str(exc)}"
