---
name: api
description: Guide for using Kimi API utilities (session management, prompts, RAG, colorful printing, threading)
---

# Kimi API Utilities Guide

This guide explains how to use the utility functions from `kimi_utils.py` and `agent_utils.py` for session management, prompting, RAG search, colorful printing, and threading.

## Session Management (kimi_utils.py)

### create_session

Create a new or resume an existing Kimi session.

```python
from kimi_utils import create_session

# Create a new session
session = create_session(
    session_id="my_session",      # Optional: unique session identifier
    work_dir=Path("./workspace"), # Optional: working directory
    skills_dir=True,              # Optional: enable skills directory
    ralph_loop=True,              # Optional: enable Ralph loop mode
    thinking=True,                # Optional: enable deep thinking
    yolo=True,                    # Optional: enable yolo mode (auto-approve)
    plan_mode=False,              # Optional: enable plan mode
    resume=False                  # Optional: resume existing session
)

# Close session when done
from kimi_utils import close_session
close_session(session)
```

### prompt

Send a prompt to the Kimi agent and get a response.

```python
from kimi_utils import prompt

# Simple prompt
prompt("What is the capital of France?")

# With options
prompt(
    "Analyze this code",
    session=session,              # Optional: use specific session
    read_agents_md=True,          # Optional: read AGENTS.md first
    skill_name="python",          # Optional: enable specific skill
    output_function=custom_print, # Optional: custom output handler
    info_print=True               # Optional: print context usage
)
```

### validate

Validate a condition using the agent.

```python
from kimi_utils import validate

# Returns True if condition is met, False otherwise
result = validate("Check if the file exists and contains 'TODO'")
```

### Context Management

```python
from kimi_utils import clear_context, print_usage

# Clear current context and start fresh
clear_context(force_create=True, resume=True)

# Print current context usage
print_usage(session)
```

## RAG Search (kimi_utils.py)

Perform semantic search on files using TextSearchIndex.

```python
from kimi_utils import rag

# Basic search
results = rag(
    query="authentication middleware",
    file_path="./src",            # Optional: path to search (default: current dir)
    top_k=5,                      # Optional: number of results (default: 5)
    content=False,                # Optional: include full file content
    refresh=False,                # Optional: force re-index
    hybrid_search=True,           # Optional: use hybrid search
    negative="deprecated"         # Optional: keywords to exclude
)

# Process results
for result in results:
    print(f"File: {result.file_path}")
    print(f"Score: {result.score}")
    print(f"Content: {result.full_content[:200]}...")
```

## Colorful Printing (agent_utils.py)

### Basic Print Functions

```python
from agent_utils import (
    print_success,    # Green - success messages
    print_error,      # Red - error messages
    print_warning,    # Yellow - warning messages
    print_info,       # Magenta - info messages
    print_debug,      # Cyan - debug messages
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
from agent_utils import colorful_print, Color, BgColor, Style

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

## Threading (agent_utils.py)

### Running Functions in Background

```python
from agent_utils import run_thread, sync_all

# Run function in background thread
def my_task(data):
    # Long running operation
    process(data)

thread = run_thread(my_task, (data,))

# Wait for all threads to complete
sync_all()
```

### Process Execution

```python
from agent_utils import _run_process_with_log, _run_process_with_error

# Run command and capture output
output, returncode = _run_process_with_log("ls -la")

# Run command and capture only errors
error_output = _run_process_with_error(
    command="npm run build",
    keycode=("error", "failed"),  # Keywords to look for
    skip_success=True             # Return None if no error keywords found
)
```

## Async Operations (kimi_utils.py)

### Async Prompt

```python
from kimi_utils import async_prompt

# Run prompt in background thread
thread = async_prompt("Analyze this file", session=False)

# Check thread status
if thread.is_alive():
    print("Still processing...")
```

### Fix Error Loop

```python
from kimi_utils import fix_error, async_fix_error

# Automatically fix errors from a command
fix_error(
    command="python main.py",
    extra_prompt="Make sure to handle edge cases",
    keycode=("error", "exception"),
    max_loop=4
)

# Async version
async_fix_error("python main.py")
```

## File Operations (kimi_utils.py)

```python
from kimi_utils import read_file, prompt_path
from pathlib import Path

# Read file content
content = read_file(Path("config.yaml"))

# Read and split by delimiter
sections = read_file(Path("docs.txt"), split_word="===SECTION===")

# Prompt with file content
prompt_path(Path("instructions.txt"))

# Prompt with split content
prompt_path(Path("tasks.txt"), split_word="---")
```

## Configuration Variables (agent_utils.py)

Default configuration values you can modify:

```python
from agent_utils import (
    _ralph_iterations,      # Max Ralph loop iterations (default: 0)
    _default_thinking,      # Deep thinking mode (default: False)
    _default_plan_mode,     # Plan mode (default: False)
    _default_yolo,          # Yolo mode (default: True)
    _default_agent_file,    # Path to agent_worker.yaml
    _default_skill_dirs,    # List of skill directories
)
```

## Complete Example

```python
"""Example script using Kimi API utilities."""
from pathlib import Path
from kimi_utils import create_session, prompt, rag, close_session
from agent_utils import print_success, print_error, print_info

# Create session
session = create_session(
    session_id="example",
    thinking=True,
    yolo=True
)

try:
    # Search for relevant code
    print_info("Searching for authentication code...")
    results = rag(
        query="auth middleware",
        file_path="./src",
        top_k=3,
        content=True
    )
    
    # Build context from results
    context = "\n\n".join([r.full_content for r in results])
    
    # Prompt with context
    prompt(
        f"Review this authentication code:\n\n{context}",
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
4. **Leverage RAG** - Use `rag()` for finding relevant code/context
5. **Background tasks** - Use `run_thread()` for long-running operations
6. **Session reuse** - Reuse sessions for related prompts to save context
7. **Clear context** - Call `clear_context()` when switching topics

## Common Imports

```python
# Core utilities
from kimi_utils import (
    create_session, close_session, prompt, 
    validate, rag, clear_context, print_usage
)
from agent_utils import (
    print_success, print_error, print_warning,
    print_info, print_debug, colorful_print,
    Color, BgColor, Style, run_thread
)

# Standard library
from pathlib import Path
import asyncio
```
