from typing import Optional, Any, Callable
from kimi_agent_sdk import Session
from kimix.base import print_success, run_process_with_error, run_thread
from .prompt import prompt
from .session import _create_default_session


def fix_error(
        command: str,
        extra_prompt: Optional[str] = None,
        skip_success: bool = True,
        keycode: tuple[str, ...] = ('error', ),
        session: Session | None = None,
        max_loop: int = 4) -> bool:
    for i in range(max_loop):
        result = run_process_with_error(
            command, keycode, skip_success=skip_success)
        if i == 0 and result is None:
            print_success('No error.')
            return True
        error_keyword = None
        for k in keycode:
            if error_keyword:
                error_keyword += ', ' + k
            else:
                error_keyword = k
        prompt_str = f'Fix "{error_keyword}" from command {command}:\n{result}\n'
        if extra_prompt is not None:
            prompt_str = f'{extra_prompt}, {prompt_str}'
        from my_tools.common import _maybe_export_output
        prompt(_maybe_export_output(prompt_str), session)
    return False


def async_prompt(
    prompt_str: str,
    session: Session | None = None,
    # settings
    read_agents_md: bool = False,
    skill_name: str | None = None,
    output_function: Callable[[str, bool], Any] | None = None,
    info_print: bool = True,
    cancel_callable: Callable[[], bool] | None = None,
) -> Any:
    session_created = None
    if session is None:
        from .session import create_session
        session = create_session()
        session_created = True
    return run_thread(prompt, (prompt_str, session, read_agents_md, skill_name, output_function, info_print, cancel_callable, session_created))


def async_fix_error(
    command: str,
    extra_prompt: Optional[str] = None,
    skip_success: bool = True,
    keycode: tuple[str, ...] = ('error',),
    session: Session | None = None
) -> Any:
    if session is None:
        session = _create_default_session()
    return run_thread(fix_error, (command, extra_prompt, skip_success, keycode, session))
