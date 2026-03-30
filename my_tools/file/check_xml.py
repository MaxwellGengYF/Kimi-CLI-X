"""XML file validator tool."""
import xml.etree.ElementTree as ET


def check_xml(file_content: str) -> str | None:
    """Validate the format of XML content.
    
    Args:
        file_content: The XML content to validate.
        
    Returns:
        None if the XML content is valid, error message string otherwise.
    """
    try:
        ET.fromstring(file_content)
        return None
    
    except ET.ParseError as exc:
        return f"XML parse error: {str(exc)}"
    except Exception as exc:
        return f"Failed to validate XML content: {str(exc)}"
