from string import Template
from kimix.kimi_utils import *
generate_memory = Template('''Please summarize our session with:
1. **Project Overview**: Brief description of the project and its purpose
2. **Key Decisions**: Important decisions made during our session
3. **Current State**: What has been completed so far
4. **Important Files**: Key code files and their roles
5. **TODOs/Pending Tasks**: Any unfinished tasks or next steps
6. **Technical Notes**: Relevant technical details to remember
Use WriteFile tool to create/update to '${memory_file}' with this structured content. Be concise but comprehensive.''')

read_memory = Template('''
read '${memory_file}' and remember.
'''.strip())


def summarize(temp_file: str | None = None) -> None:
    from pathlib import Path
    from kimix.kimi_utils import prompt, get_default_session, print_warning, clear_context
    from kimix.agent_utils import _percentage_str, print_success, print_error
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
    prompt(generate_memory.substitute(
        memory_file=temp_file), info_print=False)
    clear_context(print_info=False)
    prompt(read_memory.substitute(memory_file=temp_file), info_print=False)
    new_usage = get_default_session().status.context_usage
    print_success(
        f'Compact from {_percentage_str(last_usage)} to {_percentage_str(new_usage)}')

summarize_mistakes_prompt = Template('''Please analyze and summarize the following tool call errors:

$errors

Provide a structured summary with:
1. **Error Patterns**: Common types of errors and their causes
2. **Root Causes**: Underlying reasons for the mistakes
3. **Corrective Actions**: How to avoid or fix these errors
4. **Key Learnings**: Important takeaways for future interactions

Save this summary to: $result_file''')

def summarize_mistake(result_file: str, session = None) -> None:
    errors = get_tool_call_errors(session)
    if not errors:
        print_warning('No errors.')
        return
    from kimix.kimi_utils import prompt
    from my_tools.common import _maybe_export_output
    prompt(_maybe_export_output(summarize_mistakes_prompt.substitute(
        errors='\n'.join(str(e) for e in errors),
        result_file=result_file
    )), session=session, info_print=False)
    
def summarize_session(old_session, temp_file: str | None = None, create_session_func: Callable | None = None):
    from pathlib import Path
    from kimix.kimi_utils import prompt, print_warning
    from kimix.agent_utils import _percentage_str, print_success
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
    prompt(generate_memory.substitute(
        memory_file=temp_file), info_print=False, session=old_session)
    close_session(old_session)
    if create_session_func:
        new_session = create_session_func()
    else:
        new_session = create_session()
    prompt(read_memory.substitute(memory_file=temp_file), info_print=False, session=new_session)
    new_usage = new_session.status.context_usage
    print_success(
        f'Compact from {_percentage_str(last_usage)} to {_percentage_str(new_usage)}')

if __name__ == '__main__':
    summarize()