from string import Template
generate_memory = Template('''Please compact our session with:
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


def compact(temp_file: str | None = None) -> None:
    from pathlib import Path
    from kimi_utils import prompt, get_default_session, print_warning, clear_context
    from agent_utils import _percentage_str, print_success, print_error
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
