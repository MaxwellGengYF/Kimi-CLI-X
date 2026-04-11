---
name: tool
description: Guide for creating tools using CallableTool2 and Params pattern
---

# Tool Development Guide

This guide explains how to create custom tools using the `CallableTool2` and `Params` pattern.

## Quick Template

```python
"""Brief description of what this tool does."""
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    """Define tool parameters here."""
    required_param: str = Field(
        description="Description of this parameter for the LLM."
    )
    optional_param: str | None = Field(
        default=None,
        description="Optional parameter with default value."
    )


class MyTool(CallableTool2):
    name: str = "MyTool"              # Tool identifier
    description: str = "What this tool does."  # For LLM to understand usage
    params: type[Params] = Params     # Link to Params class

    async def __call__(self, params: Params) -> ToolReturnValue:
        """Execute the tool logic."""
        try:
            # Your tool logic here
            result = f"Processed: {params.required_param}"
            return ToolOk(output=result)
        except Exception as e:
            return ToolError(
                message=str(e),
                output="Partial output if available",
                brief="Short error summary"
            )
```

## Complete Example

```python
"""Fetch and process web content."""
import asyncio
import aiohttp
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    """Parameters for web fetch tool."""
    url: str = Field(
        description="URL to fetch content from."
    )
    timeout: float | None = Field(
        default=30.0,
        ge=1,
        le=300,
        description="Request timeout in seconds (1-300)."
    )
    max_length: int | None = Field(
        default=10000,
        description="Maximum content length to return."
    )


class WebFetch(CallableTool2):
    """Fetch web page content."""
    name: str = "WebFetch"
    description: str = "Fetch content from a URL with optional timeout and length limits."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        """Fetch URL content asynchronously."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    params.url, 
                    timeout=aiohttp.ClientTimeout(total=params.timeout)
                ) as response:
                    content = await response.text()
                    
                    # Apply length limit
                    if len(content) > params.max_length:
                        content = content[:params.max_length] + "\n... (truncated)"
                    
                    return ToolOk(output=content)
                    
        except asyncio.TimeoutError:
            return ToolError(
                message=f"Request timed out after {params.timeout}s",
                output="",
                brief="Timeout error"
            )
        except Exception as e:
            return ToolError(
                message=str(e),
                output="",
                brief="Fetch failed"
            )
```

## Params Class Reference

### Field Types

| Pattern | Description | Example |
|---------|-------------|---------|
| `param: str` | Required string | `path: str = Field(description="File path.")` |
| `param: str \| None` | Optional string | `cwd: str \| None = Field(default=None, ...)` |
| `param: list[str]` | List of strings | `args: list[str] = Field(default_factory=list, ...)` |
| `param: bool` | Boolean flag | `force: bool = Field(default=False, ...)` |
| `param: int \| float` | Numeric | `timeout: float = Field(default=30, ge=0)` |

### Field Validators

Use these in `Field()` for validation:

```python
# Numeric constraints
ge=0          # Greater than or equal to 0
le=100        # Less than or equal to 100
gt=0          # Greater than 0
lt=100        # Less than 100

# String constraints
min_length=1  # Minimum string length
max_length=255  # Maximum string length
pattern=r"^\d+$"  # Regex pattern

# Collection constraints
min_length=1  # Minimum list/dict items
max_length=10  # Maximum list/dict items
```

### Default Values

```python
# Simple default
timeout: int = Field(default=30, ...)

# Factory default (for mutable types like list, dict)
args: list[str] = Field(default_factory=list, ...)
env: dict[str, str] = Field(default_factory=dict, ...)

# Optional with None default
output_path: str | None = Field(default=None, ...)
```

## CallableTool2 Class Rules

### Required Attributes

```python
class MyTool(CallableTool2):
    name: str = "MyTool"                    # Unique identifier
    description: str = "Does something."    # LLM-visible description
    params: type[Params] = Params           # Must reference Params class
```

### The __call__ Method

```python
async def __call__(self, params: Params) -> ToolReturnValue:
    """
    Args:
        params: Instance of your Params class with validated values
    
    Returns:
        ToolOk(output="success result") on success
        ToolError(message="...", output="...", brief="...") on failure
    """
```

### Return Values

**Success:**
```python
return ToolOk(output="Your result here")
```

**Error:**
```python
return ToolError(
    message="Full error details for debugging",
    output="Partial output if any was produced",
    brief="Short error summary for display"
)
```

## Best Practices

1. **Always use type hints** - Both for Params fields and __call__ return type
2. **Write clear descriptions** - LLM uses Field descriptions to understand parameters
3. **Use proper defaults** - `default_factory=list` for lists, `default=None` for optionals
4. **Handle exceptions** - Wrap logic in try/except and return ToolError
5. **Make it async** - __call__ should always be async for consistency
6. **Validate inputs** - Use Field validators (ge, le, min_length, etc.)
7. **Keep it focused** - One tool should do one thing well
8. **Document with docstrings** - Module, class, and method docstrings

## Common Imports

```python
# Core imports (always needed)
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

# Common stdlib imports
import asyncio
import os
from pathlib import Path
from typing import Any

# For subprocess tools
import subprocess
import threading
```

## File Naming

Place your tool in the appropriate module:
- `my_tools/py/__init__.py` - Python execution tools
- `my_tools/file/run.py` - File/process tools
- `my_tools/<category>/<tool_name>.py` - Organize by category
