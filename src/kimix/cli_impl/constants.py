from typing import Any
from pathlib import Path
import os

curr_dir = Path(os.curdir)
if not curr_dir.is_absolute():
    curr_dir = curr_dir.absolute()

LSP_JSON = None
frame = 0
COMMENT = """Always write ' Start writen by AGENT ' comment before code, Always write ' End writen by AGENT ' comment after code"""

# Start writen by AGENT
HELP_STR = '''Command line options:
  -c, --clean         - Delete cache file after quit
  --no_think          - Disable thinking mode
  --plan              - Enable plan mode
  --no_yolo           - Disable YOLO mode
  -s, --skill-dir     - Specify custom skill directory
  --config            - Specify a JSON config file (see config_example.json for example)

Available commands:
  /file:<path>    - Load a file and execute its content line by line
  <path>          - Same as /file:<path>
  /clear          - Clear the conversation context
  /summarize      - Summarize conversation context to memory
  /exit           - Exit the program
  /skill          - Load skills
  /help           - Show this help message
  /context        - Print context usage
  /validate       - Test if a condition is true
  /fix:<command>  - Run a command and fix errors if any
  /txt            - input multiple line text
  /think:on       - Enable thinking mode
  /think:off      - Disable thinking mode
  /plan:on        - Enable plan mode
  /plan:off       - Disable plan mode
  /script         - Write python script
  /cmd            - Write cmd 
  /cd             - change dir

Or enter any prompt to send to the agent.
'''
# End writen by AGENT

CLEAN_MODE: bool | None = None
globals_dict: dict[str, Any] = {}
locals_dict: dict[str, Any] = {}
