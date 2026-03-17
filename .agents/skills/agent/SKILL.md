# Kimi Agent SDK Skill

This skill provides a Python SDK for interacting with Kimi AI agents, including session management, prompting, context handling, and utility functions.

## Overview

The `kimi_utils` module offers a high-level interface for:
- Creating and managing Kimi agent sessions
- Sending prompts and receiving responses
- Managing context and memory
- Running commands and fixing errors automatically
- Session persistence (save/load)

## Environment Setup

Required environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `KIMI_API_KEY` | Your Kimi API key (must start with 'sk') | Required |
| `KIMI_BASE_URL` | API base URL | `https://api.kimi.com/coding/v1` |
| `KIMI_MODEL_NAME` | Model name | `kimi-for-coding` |

## Session Management

### `create_session(session_id=None, ralph_loop=None, thinking=None, yolo=None)`

Create a new Kimi agent session.

**Parameters:**
- `session_id` (str, optional): Unique session identifier. Auto-generated if not provided.
- `ralph_loop` (bool, optional): Enable Ralph loop for iterative refinement.
- `thinking` (bool, optional): Enable thinking mode. Default: `False`.
- `yolo` (bool, optional): Enable YOLO mode for automatic execution. Default: `True`.

**Returns:** Session object

**Example:**
```python
from kimi_utils import create_session, close_session

session = create_session("my-session", thinking=True, yolo=False)
# ... use session ...
close_session(session)
```

### `close_session(session)`

Close a session and clean up resources.

**Parameters:**
- `session`: The session object to close.

### `get_default_session()`

Get the default singleton session (creates if not exists).

**Returns:** Default session object.

### `clear_context()`

Clear the context of the default session and create a fresh one.

Use this when context usage gets too high or you want to start fresh while keeping the same session identity.

## Prompting

### `prompt(prompt_str: str, session=None)`

Send a prompt to the agent and stream the response.

**Parameters:**
- `prompt_str` (str): The prompt text to send.
- `session`: Target session (uses temporary session if None).

**Example:**
```python
from kimi_utils import prompt

prompt("Explain Python decorators with examples")
```

### `async_prompt(prompt_str: str, session=None)`

Run prompt in a background thread.

**Returns:** Thread object

### `prompt_path(path: Path, split_word: str = None, session=None, after_prompt_coro=None)`

Read a file and send its contents as prompts.

**Parameters:**
- `path` (Path): Path to the file to read.
- `split_word` (str, optional): Split file content by this word and send as separate prompts.
- `session`: Target session.
- `after_prompt_coro`: Coroutine to run after each prompt segment.

## Validation & TODO Management

### `validate(prompt_str: Optional[str], session=None) -> bool`

Ask the agent to validate a condition. Returns `True` if the agent calls `SetFlag`.

**Example:**
```python
from kimi_utils import validate

is_valid = validate("Is this code Python 3 compatible?")
if is_valid:
    print("Code is valid!")
```

### `make_todo(prompt_str: Optional[str], session=None) -> bool`

Ask the agent to create a todo list. Returns `True` if `SetTodoList` was called.

**Example:**
```python
from kimi_utils import make_todo

make_todo("Create a todo list for building a REST API")
```

### `get_todo(session=None) -> list`

Get the current todo list for a session.

**Returns:** List of todo items with `title` and `status` fields.

### `clear_todo(session=None)`

Clear the todo list for a session.

## Session Persistence

### `save_session(session)`

Save and compact a session's context to persistent storage.

The agent will:
1. Summarize work completed
2. Capture key decisions
3. Record current state
4. Include relevant code snippets
5. Document lessons learned

**Example:**
```python
from kimi_utils import save_session, get_default_session

save_session(get_default_session())
```

### `load_session(session)`

Load a previously saved session context.

**Example:**
```python
from kimi_utils import load_session, get_default_session

load_session(get_default_session())
```

### `compact_session()`

Compact the default session by saving, clearing, and reloading context.

This reduces context usage while preserving session state through summarization.

**Example:**
```python
from kimi_utils import compact_session

compact_session()  # Context usage: 85% -> 15%
```

## Context Utilities

### `context_path() -> Path`

Get the path where session contexts are stored.

**Returns:** Path to `~/.kimi/sessions`

### `delete_session_dir()`

Delete all stored session data.

**Warning:** This permanently removes all saved sessions.

### `print_usage(session=None)`

Print the current context usage percentage.

## Error Fixing

### `fix_error(command: str, extra_prompt: str = None, skip_success: bool = True, keycode: tuple = ('error',), session=None, max_loop=4) -> bool`

Run a command and automatically fix errors using the agent.

**Parameters:**
- `command` (str): Command to execute.
- `extra_prompt` (str, optional): Additional context for the agent.
- `skip_success` (bool): Skip if command succeeds (exit code 0). Default: `True`.
- `keycode` (tuple): Keywords to identify errors in output. Default: `('error',)`.
- `session`: Target session.
- `max_loop` (int): Maximum fix attempts. Default: 4.

**Returns:** `True` if fixed successfully, `False` otherwise.

**Example:**
```python
from kimi_utils import fix_error

# Automatically fix Python syntax errors
fix_error("python script.py", keycode=('error', 'exception', 'traceback'))
```

### `async_fix_error(command, extra_prompt=None, skip_success=True, keycode=('error',), session=None)`

Run fix_error in a background thread.

**Returns:** Thread object

## File Utilities

### `read_file(path: Path, split_word: str = None) -> str | list`

Read a file's contents.

**Parameters:**
- `path` (Path): File path.
- `split_word` (str, optional): If provided, split content by this word.

**Returns:** File content as string, or list if split_word is provided.

## Printing Utilities

### `print_success(text: str, end: str = "\n")`
Print success message in bright green.

### `print_error(text: str, end: str = "\n")`
Print error message in bright red.

### `print_warning(text: str, end: str = "\n")`
Print warning message in bright yellow.

### `print_info(text: str, end: str = "\n")`
Print info message in bright magenta.

### `print_debug(text: str, end: str = "\n")`
Print debug message in bright cyan.

### `colorful_print(text: str, fg=None, bg=None, styles=None, end: str = "\n")`
Print with ANSI colors and styles.

**Parameters:**
- `fg`: Foreground color (Color enum)
- `bg`: Background color (BgColor enum)
- `styles`: List of Style enums

**Available Colors:**
- `Color.BLACK`, `Color.RED`, `Color.GREEN`, `Color.YELLOW`, `Color.BLUE`, `Color.MAGENTA`, `Color.CYAN`, `Color.WHITE`
- `Color.BRIGHT_*` variants

**Available Styles:**
- `Style.RESET`, `Style.BOLD`, `Style.DIM`, `Style.ITALIC`, `Style.UNDERLINE`, `Style.BLINK`, `Style.REVERSE`, `Style.HIDDEN`, `Style.STRIKETHROUGH`

## Threading Utilities

### `run_thread(function, args: tuple = None)`

Run a function in a background thread with LRU limiting (max 4 concurrent).

**Returns:** Thread object

### `sync_all()`

Wait for all background threads to complete.

## Script Execution

### `run_script(path)`

Run a Python script in a new console window.

**Returns:** subprocess.Popen object

## Configuration

### Default Values

| Setting | Default Value |
|---------|---------------|
| Reserved context size | 48,000 tokens |
| Ralph iterations | 0 (disabled) |
| Thinking mode | False |
| YOLO mode | True |
| Max processes | 4 |

### Skill Directory Resolution

The SDK looks for skills in this order:
1. `./.agents/skills`
2. `./.opencode/skills`
3. `./.config/.agents/skills`

## Complete Example

```python
from kimi_utils import (
    create_session, close_session, prompt, validate,
    make_todo, get_todo, save_session, load_session,
    compact_session, fix_error, print_success, print_error
)

# Create a session
session = create_session("dev-session", thinking=True)

try:
    # Create a todo list
    make_todo("Plan a Python web scraper project", session)
    
    # Check todo items
    todos = get_todo(session)
    for item in todos:
        print(f"[{item['status']}] {item['title']}")
    
    # Send a prompt
    prompt("Write a web scraper using requests and BeautifulSoup", session)
    
    # Validate the result
    is_secure = validate("Is the code secure against common vulnerabilities?", session)
    if not is_secure:
        prompt("Fix the security issues in the code", session)
    
    # Save session state
    save_session(session)
    
    # Compact if context is high
    compact_session()
    
    # Run and fix errors automatically
    fix_error("python scraper.py", session=session)
    
    print_success("All tasks completed!")
    
finally:
    close_session(session)
```
