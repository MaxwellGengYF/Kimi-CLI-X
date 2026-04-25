from string import Template
from kimix.base import print_warning
from typing import Callable
from kimix.utils import *


def summarize(temp_file: str | None = None) -> None:
    from pathlib import Path
    from kimix.utils import prompt, get_default_session, clear_context
    from kimix.base import percentage_str, print_success
    from my_tools.common import _create_temp_file_name
    if not get_default_session() or get_default_session().status.context_usage <= 1e-5:
        print_warning('Context is empty.')
        return
    if temp_file is None:
        temp_file = _create_temp_file_name()
    try:
        Path(temp_file).unlink(missing_ok=True)
    except:
        pass
    last_usage = get_default_session().status.context_usage
    from kimix.base import generate_memory
    lines = []
    def export_func(text: str, is_thinking: bool):
        if not is_thinking:
            lines.append(text) 
    prompt(generate_memory, info_print=False, output_function=export_func)
    clear_context(print_info=False)
    if lines:
        memory_content = '\n'.join(lines)
        prompt(f'Remember this:\n```\n{memory_content}\n```\nno tool calling, no any action', info_print=False)
    else:
        print_warning('No memory generated.')
        return
    new_usage = get_default_session().status.context_usage
    print_success(
        f'Compact from {percentage_str(last_usage)} to {percentage_str(new_usage)}')

summarize_mistakes_prompt = Template('''Please analyze and summarize the following tool call errors:
$errors
Provide a structured summary with:
1. **Error Patterns**: Common types of errors and their causes
2. **Root Causes**: Underlying reasons for the mistakes
3. **Corrective Actions**: How to avoid or fix these errors
4. **Key Learnings**: Important takeaways for future interactions''')

def summarize_mistake(result_file: str, session = None) -> None:
    errors = get_tool_call_errors(session)
    if not errors:
        print_warning('No errors.')
        return
    from kimix.utils import prompt
    from my_tools.common import _maybe_export_output
    prompt(_maybe_export_output(summarize_mistakes_prompt.substitute(
        errors='\n'.join(str(e) for e in errors),
        result_file=result_file
    )), session=session, info_print=False)
    
def summarize_session(old_session, temp_file: str | None = None, create_session_func: Callable | None = None):
    from kimix.base import generate_memory
    from pathlib import Path
    from kimix.utils import prompt
    from kimix.base import percentage_str, print_success
    from my_tools.common import _create_temp_file_name
    if old_session.status.context_usage <= 1e-5:
        print_warning('Context is empty.')
        return
    if temp_file is None:
        temp_file = _create_temp_file_name()
    try:
        Path(temp_file).unlink(missing_ok=True)
    except:
        pass
    last_usage = old_session.status.context_usage
    lines = []
    def export_func(text: str, is_thinking: bool):
        if not is_thinking:
            lines.append(text) 
    prompt(generate_memory, info_print=False, session=old_session, output_function=export_func)
    close_session(old_session)
    if create_session_func:
        new_session = create_session_func()
    else:
        new_session = create_session()
    if lines:
        memory_content = '\n'.join(lines)
        prompt(f'Remember this:\n```\n{memory_content}\n```\nno tool calling, no any action', info_print=False)
    else:
        print_warning('No memory generated.')
        return
    new_usage = new_session.status.context_usage
    print_success(
        f'Compact from {percentage_str(last_usage)} to {percentage_str(new_usage)}')

if __name__ == '__main__':
    summarize()