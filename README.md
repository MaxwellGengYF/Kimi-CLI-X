# Kimi Agent CLI

An interactive command-line interface for interacting with the Kimi AI agent.

## Prerequisites

- Set the `KIMI_API_KEY` environment variable with your Kimi API key
- Optional: Set `KIMI_BASE_URL` (defaults to `https://api.kimi.com/coding/v1`)
- Optional: Set `KIMI_MODEL_NAME` (defaults to `kimi-for-coding`)

## Usage

### Basic Usage

```bash
python kimi_agent_cli.py
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `-c`, `--clean` | Enable clean mode - delete session cache files after quitting |
| `--ralph` | Enable ralph loop mode - automatically continues working until task is complete (may consume more tokens) |
| `--no_think` | Disable thinking mode (thinking is ON by default) |
| `--no_yolo` | Disable yolo mode (auto-confirm dangerous operations; yolo is ON by default) |
| `-s`, `--skill-dir` | Specify custom skill directory |

### Examples

```bash
# Start CLI normally
python kimi_agent_cli.py

# Start with clean mode (deletes cache on exit)
python kimi_agent_cli.py -c
python kimi_agent_cli.py --clean

# Start with ralph loop mode
python kimi_agent_cli.py --ralph

# Disable thinking mode (thinking is ON by default)
python kimi_agent_cli.py --no_think

# Disable yolo mode (safer mode, requires confirmation)
python kimi_agent_cli.py --no_yolo

# Specify custom skill directory
python kimi_agent_cli.py -s /path/to/skills
python kimi_agent_cli.py --skill-dir ./my_skills

# Combine multiple options
python kimi_agent_cli.py -c --ralph --no_think --no_yolo
```

## Interactive Commands

Once the CLI is running, you can use the following commands:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear the conversation context and start fresh |
| `/compact` | Compact the conversation context to save tokens |
| `/context` | Display current context usage statistics |
| `/exit` | Exit the program |
| `/skill:<name>` | Load a specific skill from the skills directory |
| `/file:<path>` | Load and execute a Python file line by line, or read a file as prompt |
| `<path>` | Directly specify a Python file path to execute |
| `/txt` | Input multiple lines of text (end with `/end`) |
| `/todo` | Show or manage the todo list |
| `/plan:<script.py>` | Make a plan and save as executable Python script |
| `/validate:<prompt>` | Test if a condition is true |
| `/fix:<command>` | Run a command and automatically fix errors if any |

### Command Examples

```
# Send a prompt to the AI
>>>>>>>>> Enter your prompt or command:
Write a hello world program in Python

# Execute a Python file or a text file
>>>>>>>>> Enter your prompt or command:
/file:script.py
/file:my_prompt.txt

# Or simply provide the path
>>>>>>>>> Enter your prompt or command:
script.py
my_prompt.txt

# Load a skill
>>>>>>>>> Enter your prompt or command:
/skill:my-skill

# Check context usage
>>>>>>>>> Enter your prompt or command:
/context

# Clear conversation history
>>>>>>>>> Enter your prompt or command:
/clear

# Exit the CLI
>>>>>>>>> Enter your prompt or command:
/exit

# Show current todo list
>>>>>>>>> Enter your prompt or command:
/todo

# Create a plan (generates todo list)
>>>>>>>>> Enter your prompt or command:
/plan:Implement a REST API with user authentication

# Validate a condition
>>>>>>>>> Enter your prompt or command:
/validate:Is Python an interpreted language?

# Run a command and fix errors automatically
>>>>>>>>> Enter your prompt or command:
/fix:python my_script.py

# Input multiple lines of text
>>>>>>>>> Enter your prompt or command:
/txt
>>>> Start input multiple-lines, end with /end
This is line 1
This is line 2
/end

# Todo list commands
>>>>>>>>> Enter your prompt or command:
/todo:make Create a REST API with auth
/todo:done 1
/todo:in_progress 2
/todo:pending 3
```

## Agent Tools

The agent has access to various tools for file operations, code execution, web search, and more. Tools are defined in `agent_base.yaml` (basic tools) or `agent_full.yaml` (extended tools).


### File Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `ReadFile` | Read text content from a file | `path` (str): File path; `line_offset` (int): Start line; `n_lines` (int): Number of lines |
| `WriteFile` | Write content to a file | `path` (str): File path; `content` (str): Content to write; `mode` (str): "overwrite" or "append" |
| `StrReplaceFile` | Replace strings in a file | `path` (str): File path; `edit` (dict/list): Replacement specification |
| `Glob` | Find files using glob patterns | `pattern` (str): Glob pattern; `directory` (str): Search directory; `include_dirs` (bool): Include directories |
| `Grep` | Search file contents using regex | `pattern` (str): Regex pattern; `path` (str): File/directory to search; `output_mode` (str): Output format; `-n` (bool): Show line numbers; `-i` (bool): Case insensitive; `-C` (int): Context lines |
| `Ls` | List files in a directory | `directory` (str): Directory path; `long_format` (bool): Show detailed info; `recursive` (bool): List recursively |

### Code Execution

| Tool | Description | Parameters |
|------|-------------|------------|
| `Shell` | Execute shell commands (PowerShell on Windows, bash on Linux/macOS) | `command` (str): Command to execute; `timeout` (int): Timeout in seconds (1-900, default 60) |
| `Python` | Execute Python code using exec() | `code` (str): Python code; `globals_dict` (dict): Global variables; `locals_dict` (dict): Local variables |
| `CppSyntaxCheck` | Check C++ file syntax using clangd LSP | `file_path` (str): C++ file path; `project_root` (str): Project root; `clangd_path` (str): Path to clangd |

### Web Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `SearchWeb` | Search the web | Query parameters for web search |
| `FetchURL` | Fetch and extract content from a URL | `url` (str): URL to fetch |

### Task Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `SetTodoList` | Update the todo list for task tracking | `todos` (list): List of todo items with `title` and `status` ("pending", "in_progress", "done") |
| `GetTodoList` | Retrieve the current todo list | No parameters |
| `SetValue` | Set a flag (used for validation/confirmation) | No parameters |


### Archive Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `Zip` | Create a 7z archive | `source` (str): File/directory to compress; `destination` (str): Output path; `password` (str): Optional password |
| `Unzip` | Extract archives (7z/zip/rar/tar/gz) | `source` (str): Archive path; `destination` (str): Output directory; `password` (str): Optional password |

### Document Processing

| Tool | Description | Parameters |
|------|-------------|------------|
| `PdfToMarkdown` | Convert PDF documents to Markdown | `pdf_path` (str): PDF file path; `output_path` (str): Output file path; `extract_images` (bool): Extract images; `ocr` (bool): Run OCR on images; `extract_tables` (bool): Extract tables; `page_range` (str): Page range (e.g., "0-5") |
| `ImageToText` | Extract text from images using OCR | `image_path` (str): Image file path; `output_path` (str): Output text file; `language` (str): OCR language code; `preprocess` (bool): Apply image preprocessing |

### Agent Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `CreateAgent` | Create a subagent and run prompt asynchronously | `prompt` (str): Prompt to send; `session_id` (str): Optional session ID |
| `WaitAgent` | Wait for a subagent session to finish | `session_id` (str): Session ID to wait for; `timeout` (float): Timeout in seconds |
| `StoreSession` | Save session context to database | `value` (str): Context value to save |
| `LoadSession` | Load session context from database | `key` (str): Context key to load |

## Python API Usage

You can also use `kimi_utils.py` as a Python library to integrate Kimi AI into your own scripts.

### Import

```python
from kimi_utils import (
    prompt, create_session, close_session,
    clear_context, print_usage, validate,
    prompt_path, fix_error, read_file
)
```

### Session Management

| Function | Description |
|----------|-------------|
| `create_session(session_id=None)` | Create a new AI session. Auto-generates session ID if not provided. |
| `close_session(session)` | Close an existing session. |
| `get_default_session()` | Get the default session (if exists). |
| `clear_context()` | Clear the default session and create a fresh one. |
| `print_usage(session=None)` | Display context usage statistics for a session. |

### Prompt Functions

| Function | Description |
|----------|-------------|
| `prompt(prompt_str, session=None)` | Send a prompt to the AI. Creates a temporary session if none provided. |
| `async_prompt(prompt_str, session=None)` | Async version of `prompt()` - runs in a separate thread. |
| `prompt_path(path, split_word=None, session=None)` | Read a file and send its contents as a prompt. Optionally split by a delimiter. |

### Validation

| Function | Description |
|----------|-------------|
| `validate(prompt_str, session=None)` | Validate a condition by prompting the AI. Returns `True` if validation passes (AI calls SetValue tool). |

### Error Fixing

| Function | Description |
|----------|-------------|
| `fix_error(command, extra_prompt=None, skip_success=True, keycode=('error',), session=None)` | Run a command and automatically fix errors using AI. |
| `async_fix_error(...)` | Async version of `fix_error()` - runs in a separate thread. |

### Utility

| Function | Description |
|----------|-------------|
| `read_file(path, split_word=None)` | Read a file's contents. Optionally split by a delimiter. |
| `context_path()` | Get the path where session data is stored (`~/.kimi/sessions`). |
| `delete_session_dir()` | Delete all session cache files. |

### API Examples

```python
from kimi_utils import prompt, create_session, close_session, clear_context, fix_error

# Simple prompt (auto-creates temporary session)
prompt("Write a Python function to calculate fibonacci numbers")

# Using a persistent session
session = create_session("my-session")
prompt("Explain recursion", session=session)
prompt("Give me an example", session=session)  # Maintains context
close_session(session)

# Clear context when it gets too large
clear_context()

# Fix errors in a command automatically
fix_error("python my_script.py", keycode=("error", "exception"))

# Validate a condition
from kimi_utils import validate
result = validate("Is Python an interpreted language?")
print(result)  # True if AI confirms
```

### Todo Commands

| Command | Description |
|---------|-------------|
| `/todo` or `/todo:list` | Show current todo list |
| `/todo:make <prompt>` | Create a new todo list based on the prompt |
| `/todo:clear` | Clear all todo items |
| `/todo:done <n>` | Mark item(s) as done (e.g., `/todo:done 1,2` or `/todo:done 1-3`) |
| `/todo:in_progress <n>` | Mark item(s) as in_progress |
| `/todo:pending <n>` | Mark item(s) as pending |
| `/todo:help` | Show todo commands help |

## Notes

- Only `.py` files can be executed directly through the `/file` command
- The CLI maintains conversation context across prompts until `/clear` is used
- Context usage information is displayed after each AI response
- Press `Ctrl+C` (Keyboard Interrupt) at any time to interrupt the current operation or exit the CLI
