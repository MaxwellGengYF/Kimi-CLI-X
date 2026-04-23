---
name: api
description: Guide for using Kimi API utilities (session management, prompts, colorful printing, threading)
---

# Kimi API Utilities Guide

This guide explains how to use the utility functions from `kimix.kimi_utils` and `kimix.base` for session management, prompting, colorful printing, and threading.

## Session Management (kimix.kimi_utils)

### create_session

Create a new or resume an existing Kimi session.

```python
from kimix.kimi_utils import create_session
from kaos.path import KaosPath

# Create a new session
session = create_session(
    session_id="my_session",           # Optional: unique session identifier
    work_dir=KaosPath("./workspace"),  # Optional: working directory
    skills_dir=None,                   # Optional: KaosPath to skills directory
    thinking=True,                     # Optional: enable deep thinking
    yolo=True,                         # Optional: enable yolo mode (auto-approve)
    plan_mode=False,                   # Optional: enable plan mode
    resume=False,                      # Optional: resume existing session
    agent_file=None,                   # Optional: Path to custom agent_worker.yaml
    provider_dict=None,                # Optional: custom LLM provider config dict
    is_sub_agent=False                 # Optional: mark as sub-agent session
)

# Close session when done
from kimix.kimi_utils import close_session, close_session_async
close_session(session)
# Or use async version
await close_session_async(session)
```

### Default Session

```python
from kimix.kimi_utils import get_default_session, _create_default_session

# Get or create the global default session (session_id="default")
session = _create_default_session(resume=True)

# Get existing default session without creating
session = get_default_session()
```

### prompt / prompt_async

Send a prompt to the Kimi agent and get a response.

```python
from kimix.kimi_utils import prompt, prompt_async

# Simple prompt
prompt("What is the capital of France?")

# With options
prompt(
    "Analyze this code",
    session=session,                   # Optional: use specific session (None=default)
    read_agents_md=True,               # Optional: read AGENTS.md first if context is fresh
    skill_name="python",               # Optional: enable skill (str or list of str)
    output_function=custom_print,      # Optional: custom output handler for text chunks
    info_print=True,                   # Optional: print context usage after completion
    cancel_callable=None,              # Optional: callable that returns True to cancel
    close_session_after_prompt=False   # Optional: close session after prompt completes
)

# Async version (coroutine)
await prompt_async("Analyze this code", session=session)
```

### validate

Validate a condition using the agent. Appends "If the condition is true, run `Setflag` tool." internally.

```python
from kimix.kimi_utils import validate

# Returns True if agent calls Setflag, False otherwise
result = validate("Check if the file exists and contains 'TODO'", session=None)
```

### Cancel Prompt

```python
from kimix.kimi_utils import cancel_prompt, get_cancel_event

# Cancel the current prompt on a session
cancel_prompt(session)  # session=None uses default session

# Get the cancel event for custom cancellation logic
event = get_cancel_event(session)
```

### Context Management

```python
from kimix.kimi_utils import clear_context, print_usage, delete_session_dir, context_path

# Clear current context and start fresh
clear_context(force_create=True, resume=True, print_info=True)

# Print current context usage
print_usage(session)

# Get the default session context storage path
path = context_path()  # Returns ~/.kimi/sessions

# Delete all session directories (~/.kimi/sessions)
delete_session_dir()
```

### Tool Call Errors

```python
from kimix.kimi_utils import get_tool_call_errors

# Get and clear failed tool calls for a session
errors = get_tool_call_errors(session)  # or session_id string
# Returns formatted string: function, arguments, output, message
```

### Session Settings

```python
from kimix.kimi_utils import set_plan_mode

# Toggle plan mode (clears context automatically)
set_plan_mode(value=True, resume=True)
```

## Colorful Printing (kimix.base)

### Basic Print Functions

```python
from kimix.base import (
    print_success,    # Green bold - success messages
    print_error,      # Red bold - error messages
    print_warning,    # Yellow bold - warning messages
    print_info,       # Magenta bold - info messages
    print_debug,      # Cyan - debug messages (silent if _quiet=True)
    print_string,     # Plain text (respects _print_func)
)

# Usage
print_success("Operation completed successfully!")
print_error("File not found: config.yaml")
print_warning("This feature is deprecated.")
print_info("Processing step 3 of 5...")
print_debug("Variable x = 42")
```

### Advanced Color Printing

```python
from kimix.base import colorful_print, Color, BgColor, Style

# Full control over colors and styles
colorful_print(
    "Important message!",
    fg=Color.BRIGHT_RED,
    bg=BgColor.YELLOW,
    styles=[Style.BOLD, Style.UNDERLINE]
)

# Available colors
# Foreground: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE
#             BRIGHT_BLACK, BRIGHT_RED, BRIGHT_GREEN, BRIGHT_YELLOW
#             BRIGHT_BLUE, BRIGHT_MAGENTA, BRIGHT_CYAN, BRIGHT_WHITE
# Background: Same pattern with BgColor
# Styles: RESET, BOLD, DIM, ITALIC, UNDERLINE, BLINK, REVERSE, HIDDEN, STRIKETHROUGH
```

### Print Agent JSON

```python
from kimix.base import print_agent_json

# Pretty-print streaming messages from the agent session
print_agent_json(
    get_message=lambda: message.model_dump_json(),
    output_function=custom_handler  # Optional: callback for text content
)
```

## Threading (kimix.base)

### Running Functions in Background

```python
from kimix.base import run_thread, sync_all

# Run function in background thread (max 8 concurrent)
def my_task(data):
    # Long running operation
    process(data)

thread = run_thread(my_task, (data,))

# Wait for all threads to complete
sync_all()
```

### Async Prompt Helpers

```python
from kimix.kimi_utils import async_prompt, async_fix_error

# Run prompt in background thread (creates new session if None, closes after)
thread = async_prompt("Analyze this file", session=None)

# Run fix_error in background thread
thread = async_fix_error("python main.py", extra_prompt="Handle edge cases")
```

### Process Execution

```python
from kimix.base import _run_process_with_log, run_process_with_error, run_script

# Run command and capture output
output, returncode = _run_process_with_log("ls -la")

# Run command and capture only errors
error_output = run_process_with_error(
    command="npm run build",
    keycode=("error", "failed"),     # Keywords to look for in output
    skip_success=True                # Return None if no error keywords found and code==0
)

# Run a Python script in a new console window
proc = run_script("./script.py")
```

## File Operations (kimix.kimi_utils)

```python
from kimix.kimi_utils import read_file, prompt_path
from pathlib import Path

# Read file content
content = read_file(Path("config.yaml"))

# Read and split by delimiter
sections = read_file(Path("docs.txt"), split_word="===SECTION===")

# Prompt with file content
prompt_path(Path("instructions.txt"))

# Prompt with split content and optional coroutine callback
prompt_path(
    Path("tasks.txt"),
    split_word="---",
    session=session,
    after_prompt_coro=generator_func  # Optional: generator called after each chunk
)
```

## Error Fix Loop (kimix.kimi_utils)

```python
from kimix.kimi_utils import fix_error

# Automatically detect and fix errors from a command
fix_error(
    command="python main.py",
    extra_prompt="Make sure to handle edge cases",  # Optional: extra instructions
    keycode=("error", "exception"),                  # Optional: keywords to detect
    skip_success=True,                               # Optional: skip if return code is 0
    session=None,                                    # Optional: session to use
    max_loop=4                                       # Optional: max fix attempts
)
```

## Configuration Variables (kimix.base)

Default configuration values you can import and modify:

```python
from kimix.base import (
    _default_thinking,       # Deep thinking mode (default: True)
    _default_plan_mode,      # Plan mode (default: False)
    _default_yolo,           # Yolo mode (default: True)
    _default_agent_file,     # Path to agent_worker.yaml
    _default_skill_dirs,     # List of skill directories
    _default_provider,       # Custom provider dict or None
    _quiet,                  # If True, suppresses print_debug
    _colorful_print,         # If False, disables ANSI colors
    _print_func,             # Optional custom print handler (text, end) -> None
)
```

### Configuration Setters

```python
from kimix.base import (
    set_default_thinking,
    set_default_plan_mode,
    set_default_yolo,
    set_default_agent_file_dir,
    set_default_agent_file,
    set_default_skill_dirs,
    set_default_provider,
)

# Set default configuration values
set_default_thinking(True)
set_default_plan_mode(False)
set_default_yolo(True)
set_default_agent_file_dir(Path("./custom_agents"))
set_default_agent_file(Path("./custom_agent.yaml"))
set_default_skill_dirs(["./skills", "./more_skills"])
set_default_provider({"name": "custom", "api_key": "..."})
```

### Skill Directories

```python
from kimix.base import get_skill_dirs

# Auto-discover skill directories (checked paths: .agents/skills, .config/.agents/skills, .opencode/skills)
dirs = get_skill_dirs(use_kaos_path=True)
```

### Utility Functions

```python
from kimix.base import percentage_str

# Format number as percentage string
s = percentage_str(0.7533)  # Returns "75.3%"
```

### Path Utilities

```python
from kimix.kimi_utils import make_kaos_dir
from kaos.path import KaosPath

# Convert any path to KaosPath
kaos_path = make_kaos_dir("./my_folder")
```

## Complete Example

```python
"""Example script using Kimi API utilities."""
from pathlib import Path
from kimix.kimi_utils import create_session, prompt, close_session, clear_context
from kimix.base import print_success, print_error, print_info

# Create session
session = create_session(
    session_id="example",
    thinking=True,
    yolo=True
)

try:
    # Prompt with custom message
    prompt(
        "Review this authentication code",
        session=session
    )
    
    print_success("Analysis complete!")
    
except Exception as e:
    print_error(f"Error: {e}")
    
finally:
    close_session(session)
```

## Best Practices

1. **Always close sessions** - Use `close_session()` when done to free resources
2. **Use colorful prints** - Makes output more readable and organized
3. **Handle errors** - Wrap prompts in try/except blocks
4. **Background tasks** - Use `run_thread()` for long-running operations
6. **Session reuse** - Reuse sessions for related prompts to save context
7. **Clear context** - Call `clear_context()` when switching topics
8. **Validate conditions** - Use `validate()` for yes/no checks via the agent
9. **Fix errors automatically** - Use `fix_error()` for iterative debugging
10. **Skill directories** - Place skills in `.agents/skills/` for auto-discovery
11. **Cancel long prompts** - Use `cancel_prompt()` to stop running prompts

## Common Imports

```python
# Core utilities
from kimix.kimi_utils import (
    create_session, close_session, close_session_async,
    prompt, prompt_async, validate, clear_context, print_usage,
    get_default_session, get_tool_call_errors,
    set_plan_mode, cancel_prompt, get_cancel_event,
    read_file, prompt_path, fix_error, async_prompt, async_fix_error,
    context_path, delete_session_dir, make_kaos_dir
)
from kimix.base import (
    print_success, print_error, print_warning,
    print_info, print_debug, colorful_print,
    Color, BgColor, Style, run_thread, sync_all,
    run_process_with_error, get_skill_dirs, percentage_str,
    set_default_thinking, set_default_plan_mode, set_default_yolo,
    set_default_agent_file, set_default_skill_dirs, set_default_provider
)

# Standard library
from pathlib import Path
import asyncio
```
