from typing import Any, Optional
import asyncio
from pathlib import Path
import os
from kaos.path import KaosPath
from kimi_agent_sdk import Session
import kimix.base as base
from kimix.base import print_success, print_debug, percentage_str
from . import _globals
from .config import _create_config
from .system_prompt import get_system_prompt


def context_path() -> Path:
    user_home = Path.home()
    return user_home / '.kimi' / 'sessions'


def delete_session_dir() -> None:
    import shutil
    path = context_path()
    if path.exists():
        shutil.rmtree(path)
        print_success(f'{str(path)} deleted.')


def make_kaos_dir(obj: Any) -> KaosPath:
    if type(obj) is not KaosPath:
        return KaosPath(obj)
    return obj


def _ensure_skill_dirs(skill_dirs: Any) -> list[KaosPath]:
    from collections.abc import Iterable
    if skill_dirs is None:
        return []
    if type(skill_dirs) == list:
        return [make_kaos_dir(i) for i in skill_dirs]
    if isinstance(skill_dirs, Iterable) and not isinstance(skill_dirs, (str, bytes)):
        return [make_kaos_dir(i) for i in skill_dirs]
    return [make_kaos_dir(skill_dirs)]


async def _create_session_async(
    session_id: Optional[str] = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[KaosPath] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[Path] = None,
    resume: bool = False,
    plan_mode: Optional[bool] = None,
    provider_dict: dict[str, Any] | None = None,
    is_sub_agent: bool = False,
) -> Session:
    if session_id is None:
        session_id = str(_globals._session_idx)
        _globals._session_idx += 1
    tool_call_failed_list: list[Any] = list()
    base._tool_call_failed_lists[session_id] = tool_call_failed_list
    cfg = _create_config(provider_dict)
    session = None
    if agent_file is None:
        agent_file = base._default_agent_file
    else:
        if type(agent_file) is not Path:
            agent_file = Path(agent_file)
        if not agent_file.is_absolute():
            agent_file = Path(__file__).parent.parent / agent_file
    skills_dirs = _ensure_skill_dirs(skills_dir) if skills_dir is not None else base.get_skill_dirs()
    if resume:
        session = await Session.resume(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else KaosPath(os.curdir),
            skills_dirs=skills_dirs,
            yolo=yolo if yolo is not None else base._default_yolo,
            plan_mode=plan_mode if plan_mode is not None else base._default_plan_mode,
            thinking=thinking if thinking is not None else base._default_thinking,
            config=cfg,
            agent_file=agent_file,
            tool_call_failed_list=tool_call_failed_list,
            custom_system_prompt=get_system_prompt(
                is_sub_agent, plan_mode, yolo, work_dir, skills_dirs),
        )
        if not session:
            print_debug(f'Session {session_id} not found.')
    if not session:
        session = await Session.create(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else KaosPath(os.curdir),
            skills_dirs=skills_dirs,
            yolo=yolo if yolo is not None else base._default_yolo,
            plan_mode=plan_mode if plan_mode is not None else base._default_plan_mode,
            thinking=thinking if thinking is not None else base._default_thinking,
            config=cfg,
            agent_file=agent_file,
            tool_call_failed_list=tool_call_failed_list,
            custom_system_prompt=get_system_prompt(
                is_sub_agent, plan_mode, yolo, work_dir, skills_dirs),
        )
    return session


def create_session(
    session_id: Optional[str] = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[KaosPath] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[Path] = None,
    resume: bool = False,
    plan_mode: Optional[bool] = None,
    provider_dict: dict[str, Any] | None = None,
) -> Session:
    return asyncio.run(_create_session_async(
        session_id,
        work_dir,
        skills_dir,
        thinking,
        yolo,
        agent_file,
        resume,
        plan_mode,
        provider_dict
    ))


def get_tool_call_errors(session: Session | str | None = None) -> str:
    if session is None:
        id = 'default'
    elif isinstance(session, str):
        id = session
    else:
        id = session.id
    lst = base._tool_call_failed_lists.get(id, None)
    s = ''
    if lst:
        for i in lst:
            # tuple: function-name, arguments, output, message
            s += f'- function: {i[0]}\n- arguments: {i[1]}\n- output: {i[2]}\n- message: {i[3]}'
        lst.clear()
    return s


def close_session(session: Session) -> None:
    if not session:
        return
    try:
        del base._tool_call_failed_lists[session.id]
    except:
        pass
    asyncio.run(session.close())


async def close_session_async(session: Session) -> None:
    if not session:
        return
    try:
        del base._tool_call_failed_lists[session.id]
    except:
        pass
    await session.close()


def get_cancel_event(session: Session | None = None) -> asyncio.Event | None:
    """Get the cancel event of a session."""
    if session is None:
        session = get_default_session()
    return getattr(session, '_cancel_event', None)


def cancel_prompt(session: Session | None = None) -> None:
    """Set the cancel event on a session to cancel the current prompt."""
    if session is None:
        session = get_default_session()
    if session is not None:
        session.cancel()


def get_default_session() -> Session | None:
    return _globals._default_session


def _create_default_session(resume: bool = True) -> Session:
    if _globals._default_session:
        return _globals._default_session
    _globals._default_session = create_session("default", resume=resume)
    return _globals._default_session


def _print_usage(session: Session, time_seconds: float | None = None) -> None:
    if not getattr(_globals._should_print_usage, 'value', False):
        return
    s = percentage_str(session.status.context_usage)
    if time_seconds is not None:
        hours = int(time_seconds) // 3600
        minutes = (int(time_seconds) % 3600) // 60
        seconds = int(time_seconds) % 60
        time_text = f'  time: {hours}:{minutes:02d}:{seconds:02d}'
    else:
        time_text = ''
    print_success(
        f'Finished, context usage: {s}{time_text}'
    )


def print_usage(session: Session | None = None) -> None:
    if session is None:
        session = _create_default_session()
    s = percentage_str(session.status.context_usage)
    print_success(
        f'Context usage: {s}'
    )


def clear_context(force_create: bool = False, resume: bool = False, print_info: bool = True) -> None:
    if _globals._default_session:
        if not force_create and _globals._default_session.status.context_usage < 1e-8:
            if print_info:
                _print_usage(_globals._default_session)
            return
        elif _globals._default_session is not None:
            asyncio.run(_globals._default_session.close())
        _globals._default_session = None
    session = _create_default_session(resume)
    if print_info:
        _print_usage(session)
