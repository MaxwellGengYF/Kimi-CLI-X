from typing import Any, Callable, Optional
import asyncio
from pathlib import Path
from kimi_agent_sdk import Session
import kimix.base as base
from kimix.base import print_debug, print_warning, print_error, print_agent_json
from . import _globals
from .session import close_session_async, _create_default_session, _print_usage


async def prompt_async(
    prompt_str: str,
    session: Session | None = None,
    # settings
    read_agents_md: bool = False,
    skill_name: str | None = None,
    output_function: Callable[[Any], Any] | None = None,
    info_print: bool = True,
    cancel_callable: Callable[[], bool] | None = None,
    close_session_after_prompt: bool = False,
) -> None:
    if session is None:
        session = _create_default_session()
        close_session_after_prompt = False
    prompt_str = prompt_str.strip()
    try:
        def enable_skill(skill_name: str) -> None:
            nonlocal prompt_str
            if not base._default_skill_dirs:
                print_warning('Skill dir not setted.')
            else:
                skill_found = False
                for skill_dir in base._default_skill_dirs:
                    if (Path(str(skill_dir)) / Path(skill_name) / 'SKILL.md').exists():
                        skill_found = True
                        break
                if not skill_found:
                    print_warning(f'Skill {skill_name} not found.')
                else:
                    prompt_str = f'Use skill:{skill_name}.\n' + prompt_str
        if skill_name:
            try:
                for i in skill_name:
                    enable_skill(i)
            except:
                enable_skill(skill_name)
        if session.status.context_usage < 1e-4 and read_agents_md and Path('AGENTS.md').exists():
            prompt_str = f'Read AGENTS.md.\n' + prompt_str

        if info_print:
            print_debug(f'Start...', end='\n\n')

        max_retries = 5
        for attempt in range(max_retries):
            # already canceled.
            if session._cancel_event is not None and session._cancel_event.is_set():
                break
            try:
                import time
                start_time = time.time()
                async for message in session.prompt(prompt_str,merge_wire_messages=True):
                    if cancel_callable is not None and cancel_callable():
                        session.cancel()
                        break
                    print_agent_json(
                        lambda: message.model_dump_json(), output_function)
                if info_print:
                    end_time = time.time()
                    _print_usage(session, end_time - start_time)
                break
            except KeyboardInterrupt as e:
                if session:
                    session.cancel()
            except Exception as e:
                print_error(str(e))
                if session:
                    session.cancel()
                if "429" in str(e) or "400" in str(e) or "500" in str(e) or "502" in str(e) or "503" in str(e):
                    wait_time = min(2 ** attempt, 60)
                    print_warning(f"Rate limited. Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                elif attempt == max_retries - 1:
                    raise
                else:
                    await asyncio.sleep(1)
    finally:
        if close_session_after_prompt and session:
            await close_session_async(session)


def prompt(
    prompt_str: str,
    session: Session | None = None,
    # settings
    read_agents_md: bool = False,
    skill_name: str | None = None,
    output_function: Callable[[Any], Any] | None = None,
    info_print: bool = True,
    cancel_callable: Callable[[], bool] | None = None,
    close_session_after_prompt: bool = False,
) -> None:
    asyncio.run(
        prompt_async(
            prompt_str,
            session,
            # settings
            read_agents_md,
            skill_name,
            output_function,
            info_print,
            cancel_callable,
            close_session_after_prompt,
        ))


def validate(
    prompt_str: Optional[str], session: Session | None = None
) -> bool:
    if type(prompt_str) == str and len(prompt_str) > 0:
        import my_tools.flag as flag
        flag.reset_flag()
        prompt_str = prompt_str + \
            '\n\nIf the condition is true, run `Setflag` tool.'
        prompt(prompt_str, session)
        return flag.check_flag() is not None
    else:
        return False


def prompt_path(path: Path, split_word: Optional[str] = None, session: Session | None = None, after_prompt_coro: Any = None) -> None:
    f = open(path, 'r', encoding='utf-8')
    if not f:
        print_error(f'File {str(path)} not found.')
        return
    s = f.read()
    f.close()
    coro = None
    if after_prompt_coro is not None:
        coro = after_prompt_coro()
    if split_word:
        words = s.strip().split(split_word)
        for i in words:
            prompt(i, session=session)
            if coro is not None:
                try:
                    coro.next()
                except StopIteration as e:
                    coro = None
    else:
        prompt(s, session=session)
        if coro is not None:
            try:
                coro.next()
            except StopIteration as e:
                coro = None
