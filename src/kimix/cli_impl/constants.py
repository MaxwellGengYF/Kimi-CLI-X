from typing import Any
from pathlib import Path
import os

from kimix.base import colorful_text, Color

curr_dir = Path(os.curdir)
if not curr_dir.is_absolute():
    curr_dir = curr_dir.absolute()

LSP_JSON = None
frame = 0
COMMENT = """Always write ' Start writen by AGENT ' comment before code, Always write ' End writen by AGENT ' comment after code"""

# Start writen by AGENT
HELP_STR = f'''Command line options:
  -c, --clean         - Delete cache file after quit
  --no_think          - Disable thinking mode
  --plan              - Enable plan mode
  --no_yolo           - Disable YOLO mode
  -s, --skill-dir     - Specify custom skill directory
  --config            - Specify a JSON config file (see config_example.json for example)

Available commands:
  {colorful_text('/file:<path>', fg=Color.YELLOW)}    - Load a file and execute its content line by line
  <path>          - Same as /file:<path>
  {colorful_text('/clear', fg=Color.YELLOW)}          - Clear the conversation context
  {colorful_text('/summarize', fg=Color.YELLOW)}      - Summarize conversation context to memory
  {colorful_text('/exit', fg=Color.YELLOW)}           - Exit the program
  {colorful_text('/skill', fg=Color.YELLOW)}          - Load skills
  {colorful_text('/help', fg=Color.YELLOW)}           - Show this help message
  {colorful_text('/context', fg=Color.YELLOW)}        - Print context usage
  {colorful_text('/fix:<command>', fg=Color.YELLOW)}  - Run a command and fix errors if any
  {colorful_text('/txt', fg=Color.YELLOW)}            - input multiple line text
  {colorful_text('/think:on', fg=Color.YELLOW)}       - Enable thinking mode
  {colorful_text('/think:off', fg=Color.YELLOW)}      - Disable thinking mode
  {colorful_text('/plan:on', fg=Color.YELLOW)}        - Enable plan mode
  {colorful_text('/plan:off', fg=Color.YELLOW)}       - Disable plan mode
  {colorful_text('/todo', fg=Color.YELLOW)}           - Start a long-term task, use agent-list
  {colorful_text('/script', fg=Color.YELLOW)}         - Write python script
  {colorful_text('/cmd', fg=Color.YELLOW)}            - Write cmd 
  {colorful_text('/cd', fg=Color.YELLOW)}             - change dir
  {colorful_text('/swarm:<task>', fg=Color.YELLOW)}  - Execute swarm task with multiple agents

Or enter any prompt to send to the agent.
'''
# End writen by AGENT

CLEAN_MODE: bool | None = None
globals_dict: dict[str, Any] = {}
locals_dict: dict[str, Any] = {}
