---
name: default
---
# Writing Tools for Kimi Agent SDK

This guide shows how to write tool classes using the Kimi Agent SDK pattern.

## Basic Structure

A tool consists of two parts:
1. **Params class** (`XxxParams`): Pydantic model defining tool parameters
2. **Tool class**: Implements the tool logic by inheriting from `CallableTool2`

## Minimal Example

```python
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class GreetParams(BaseModel):
    """Parameters for the Greet tool."""
    name: str = Field(
        description="Name of the person to greet.",
    )
    times: int = Field(
        default=1,
        description="Number of times to greet.",
    )


class Greet(CallableTool2):
    """A simple greeting tool."""
    name: str = "Greet"
    description: str = "Greet a person by name."
    params: type[GreetParams] = GreetParams

    async def __call__(self, params: GreetParams) -> ToolReturnValue:
        """Execute the greeting."""
        try:
            greeting = "\n".join([f"Hello, {params.name}!" for _ in range(params.times)])
            return ToolOk(output=greeting)
        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to greet: {str(exc)}",
                brief="Greet failed",
            )
```

## Params Class

The params class defines what arguments the tool accepts:

```python
from pydantic import BaseModel, Field
from typing import Literal


class RunParams(BaseModel):
    # Required parameter - no default value
    path: str = Field(
        description="The path to the executable to run.",
    )
    
    # Optional parameter with default factory
    args: list[str] = Field(
        default_factory=list,
        description="List of arguments to pass to the executable.",
    )
    
    # Optional parameter with default value
    timeout: int | None = Field(
        default=120,
        description="Timeout in seconds. If not specified, no timeout is applied.",
    )
    
    # Boolean parameter
    detect_input: bool = Field(
        default=False,
        description="Enable Detect input mode, if process requires input, early return.",
    )
    
    # Literal for enum-like values
    mode: Literal["overwrite", "append"] = Field(
        default="overwrite",
        description="The mode to use to write to the file.",
    )
```

### Params Class Guidelines

- Use `Field(description=...)` for all fields - descriptions are shown to the LLM
- Use type hints: `str`, `int`, `bool`, `list[str]`, `str | None`, etc.
- Set meaningful defaults for optional parameters
- Use `default_factory=list` for mutable defaults

## Tool Class

The tool class implements the execution logic:

```python
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue


class MyTool(CallableTool2):
    # Tool name - used to identify the tool
    name: str = "MyTool"
    
    # Description - shown to the LLM to explain what the tool does
    description: str = "Description of what this tool does."
    
    # Reference to the params class
    params: type[MyParams] = MyParams

    async def __call__(self, params: MyParams) -> ToolReturnValue:
        """Main execution method. Must return ToolReturnValue."""
        # Implementation here
        pass
```

### Generic Version (for type checking)

```python
from kimi_agent_sdk import CallableTool2


class MyTool(CallableTool2[MyParams]):
    name: str = "MyTool"
    description: str = "Description..."
    params: type[MyParams] = MyParams
    
    async def __call__(self, params: MyParams) -> ToolReturnValue:
        ...
```

## Return Values

Tools must return a `ToolReturnValue`:

### Success

```python
from kimi_agent_sdk import ToolOk

return ToolOk(
    output="The result of the tool execution",
    message="Optional success message",  # Optional
    brief="Optional brief summary",      # Optional
)
```

### Error

```python
from kimi_agent_sdk import ToolError

return ToolError(
    output="Partial output if available",  # Can be empty string
    message="Detailed error message explaining what went wrong",
    brief="Short error summary",  # Shown in brief mode
)
```

## Tool with No Parameters

```python
from pydantic import BaseModel


class NoParams(BaseModel):
    pass


class Reset(CallableTool2):
    name: str = "Reset"
    description: str = "Reset the internal state."
    params: type[NoParams] = NoParams

    async def __call__(self, params: NoParams) -> ToolReturnValue:
        # Reset logic here
        return ToolOk(output="State reset successfully")
```

## Tool with Constructor Dependencies

```python
from kimi_agent_sdk import CallableTool2
from kimi_cli.soul.agent import BuiltinSystemPromptArgs
from kimi_cli.soul.approval import Approval


class WriteFile(CallableTool2[Params]):
    name: str = "WriteFile"
    description: str = "Write a file."
    params: type[Params] = Params

    def __init__(self, builtin_args: BuiltinSystemPromptArgs, approval: Approval):
        super().__init__()
        self._work_dir = builtin_args.KIMI_WORK_DIR
        self._approval = approval

    async def __call__(self, params: Params) -> ToolReturnValue:
        # Use self._work_dir and self._approval here
        pass
```

## Loading Description from File

```python
from pathlib import Path
from kimi_cli.tools.utils import load_desc


class MyTool(CallableTool2):
    name: str = "MyTool"
    description: str = load_desc(Path(__file__).parent / "my_tool.md")
    params: type[MyParams] = MyParams
```

## Complete Real-World Example

```python
"""KillProcess tool for terminating the currently running process."""
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel


class KillParams(BaseModel):
    """No parameters needed for KillProcess."""
    pass


class KillProcess(CallableTool2):
    """Kill the currently running process."""
    name: str = "KillProcess"
    description: str = "Kill the currently running process."
    params: type[KillParams] = KillParams

    async def __call__(self, params: KillParams) -> ToolReturnValue:
        """Kill the running process."""
        state = get_state()  # Get shared state

        if state.process is None:
            return ToolError(
                output="",
                message="No process is currently running.",
                brief="No active process",
            )

        try:
            state.process.kill()
            state.process.wait()
            output = get_final_output()
            return ToolOk(
                output=output,
                message="Process killed successfully",
                brief="Process killed",
            )
        except Exception as exc:
            return ToolError(
                output=get_final_output(),
                message=f"Failed to kill process: {str(exc)}",
                brief="Kill failed",
            )
```

## Key Points

1. **Always use `Field(description=...)`** - LLM needs descriptions to use tools correctly
2. **Always return `ToolReturnValue`** - Use `ToolOk` for success, `ToolError` for failures
3. **Keep `__call__` async** - Tools may need to do I/O operations
4. **Provide meaningful error messages** - Help users understand what went wrong
5. **Use type hints** - Helps with IDE support and runtime validation via Pydantic
