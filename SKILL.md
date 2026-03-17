# Coding skill

```python
from kimi_utils import *

# Send a prompt to the AI agent and stream the response
# This function creates/uses a session, sends the prompt, and prints agent output
prompt('''Your prompt...''')

# Validate a condition by prompting the AI
# Returns True if the AI calls SetFlag tool (indicating condition is true), False otherwise
if validate('''condition...'''):
    pass

# Automatically detect and fix errors from a shell command
# Runs the command repeatedly, prompting AI to fix any "error" found in output
# Stops when no errors remain or max_loop (default 4) iterations reached
fix_error('shell command')
```
