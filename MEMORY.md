# Shell Tool Background Task Usage Summary

## Reference File
- `D:\kimi-test\kimi-cli\src\kimi_cli\tools\shell\__init__.py`

## Overview
The `Shell` tool class demonstrates how to implement `run_in_background` functionality in a tool class.

## Key Components

### 1. Parameter Definition (Params class)
```python
run_in_background: bool = Field(
    default=False,
    description="Whether to run the command as a background task.",
)
description: str = Field(
    default="",
    description="A short description for the background task. Required when run_in_background=true.",
)
```

**Validation Rules:**
- When `run_in_background=true`, `description` is required (enforced via `@model_validator`)
- Foreground commands: max timeout = 5 minutes (`MAX_FOREGROUND_TIMEOUT`)
- Background commands: max timeout = 24 hours (`MAX_BACKGROUND_TIMEOUT`)

### 2. Execution Routing
In the `__call__` method, check the flag and route accordingly:
```python
if params.run_in_background:
    return await self._run_in_background(params)
# ... foreground execution logic
```

### 3. Background Task Implementation

#### Step 1: Get Tool Call Context
```python
tool_call = get_current_tool_call_or_none()
if tool_call is None:
    return ToolResultBuilder().error("Background shell requires a tool call context.", ...)
```

#### Step 2: Request Approval
Background tasks still require user approval before execution.

#### Step 3: Create Background Task via Runtime
```python
view = self._runtime.background_tasks.create_bash_task(
    command=params.command,
    description=params.description.strip(),
    timeout_s=params.timeout,
    tool_call_id=tool_call.id,
    shell_name="...",
    shell_path="...",
    cwd="...",
)
```

#### Step 4: Return Formatted Response
Use `ToolResultBuilder` to construct a response with:
- Task metadata (via `format_task()`)
- Guidance for next steps (automatic notification, TaskOutput usage hints)
- Display block for UI rendering (`BackgroundTaskDisplayBlock`)

## Pattern Summary

```python
class Params(BaseModel):
    run_in_background: bool = Field(default=False, description="...")
    description: str = Field(default="", description="Required when run_in_background=true")
    
    @model_validator(mode="after")
    def validate(self) -> Self:
        if self.run_in_background and not self.description:
            raise ValueError("description required for background tasks")
        return self

class MyTool(CallableTool2[Params]):
    async def __call__(self, params: Params) -> ToolReturnValue:
        if params.run_in_background:
            return await self._run_in_background(params)
        return await self._run_foreground(params)
    
    async def _run_in_background(self, params: Params) -> ToolReturnValue:
        tool_call = get_current_tool_call_or_none()
        # ... create task via runtime.background_tasks
        # ... return formatted response
```

## Dependencies Required
- `kimi_cli.background.TaskView`, `format_task`
- `kimi_cli.soul.toolset.get_current_tool_call_or_none`
- `kimi_cli.tools.display.BackgroundTaskDisplayBlock`
- `kimi_cli.tools.utils.ToolResultBuilder`
