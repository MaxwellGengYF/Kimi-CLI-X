import kimi_agent_sdk
from agent_utils import *
from agent_utils import _run_process_with_error, _percentage_str
from kaos.path import KaosPath
import sys
import asyncio
import time
from pathlib import Path

_last_call_time = time.time()


def _check_legal(value, start_with):
    if value is None or type(value) != str:
        return False
    return value.startswith(start_with)


api_key = os.environ.get("KIMI_API_KEY")
if not _check_legal(api_key, 'sk'):
    print_error('API key shoud be setted to KIMI_API_KEY environment var')
    exit(1)

if not _check_legal(os.environ.get("KIMI_BASE_URL"), 'http'):
    os.environ["KIMI_BASE_URL"] = "https://api.kimi.com/coding/v1"
_default_model = 'kimi-for-coding'
_config_model = os.environ.get("KIMI_MODEL_NAME")
if not _check_legal(_config_model, 'kimi'):
    os.environ['KIMI_MODEL_NAME'] = _default_model
elif _config_model != _default_model:
    _default_model = _config_model
    print_debug(f'Using {_config_model} model.')

default_work_dir = KaosPath(os.curdir)

_config = None
_default_session = None

agent_file = Path(__file__).parent / 'agent.yaml'

# init


def _init_model():
    global _config
    if _config:
        return
    from kimi_agent_sdk import Config
    from kimi_cli.config import LoopControl
    _config = Config()
    _config.default_thinking = True
    _config.default_yolo = True
    if not _config.loop_control:
        _config.loop_control = LoopControl()
    # This is just my favor
    _config.loop_control.max_steps_per_turn = 1000
    _config.loop_control.max_retries_per_step = 32
    _config.loop_control.max_ralph_iterations = -1
    _config.loop_control.reserved_context_size = 5_000


def create_session(work_dir: KaosPath = None, skills_dir: KaosPath = None, session_id: str = None):
    global agent_file
    from kimi_agent_sdk import Session
    _init_model()
    if work_dir is None:
        work_dir = default_work_dir
    if skills_dir is None:
        skills_dir = work_dir / '.agents/skills'
    if not (asyncio.run(skills_dir.exists())):
        skills_dir = None

    async def func():
        nonlocal session_id
        session = await Session.create(
            session_id=session_id,
            work_dir=work_dir,
            yolo=True,
            thinking=True,
            skills_dir=skills_dir,
            config=_config,
            agent_file=agent_file
        )
        return session
    return asyncio.run(func())


def _create_default_session(work_dir: KaosPath = None, skills_dir: KaosPath = None):
    global _default_session
    if _default_session:
        return _default_session
    _default_session = create_session(work_dir, skills_dir, "default")
    return _default_session


def _print_usage(session):
    s = _percentage_str(session.status.context_usage)
    print_success(
        f'Finished, context usage: {s}%'
    )


def print_usage(session=None):
    if not session:
        session = _create_default_session()
    s = _percentage_str(session.status.context_usage)
    print_success(
        f'Context usage: {s}%'
    )


def clear_context():
    global _default_session
    if _default_session:
        if _default_session.status.context_usage < 1e-8:
            _print_usage(_default_session)
            return
        else:
            asyncio.run(_default_session.close())
        _default_session = None
    _create_default_session()
    _print_usage(_default_session)


def compact_context(session=None):
    from kimi_agent_sdk import TextPart
    if session is None:
        session = _create_default_session()
    last_usage = session.status.context_usage
    if last_usage < 1e-8:
        _print_usage(_default_session)
        return
    async def func():
        nonlocal session
        async for message in session.prompt(
            user_input='/compact',
            merge_wire_messages=True
        ):
            match message:
                case TextPart(text=text):
                    print_success(text)
    asyncio.run(func())
    cur_usage = session.status.context_usage
    print_success(
        f'Context compressed from {_percentage_str(last_usage)}% to {_percentage_str(cur_usage)}%'
    )


def skill(skill_str: str, session=None):
    if session is None:
        session = _create_default_session()

    async def func():
        import time
        max_retries = 5
        for attempt in range(max_retries):
            print_debug(f'Loading skill: {skill_str}', end='\n\n')
            try:
                async for message in session.prompt(
                    '/skill:' + skill_str,
                    merge_wire_messages=True,
                ):
                    print_agent_json(lambda: message.model_dump_json())
            except Exception as e:
                if "429" in str(e):
                    wait_time = 4 ** attempt  # 1, 4, 16, 64, 128 秒
                    print_warning(f"Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
            break

    asyncio.run(func())
    _print_usage(session)


def prompt(prompt_str: str, session=None, create_session: bool = False):
    global _default_session
    prompt_str = prompt_str.strip()
    if session is None:
        if create_session:
            session = create_session()
        else:
            session = _create_default_session()
    else:
        create_session = False

    async def func():
        try:
            nonlocal session
            max_retries = 5
            for attempt in range(max_retries):
                if len(prompt_str) > 50:
                    print_debug(f'Prompt: {prompt_str[:50]}...', end='\n\n')
                else:
                    print_debug(f'Prompt: {prompt_str}', end='\n\n')
                try:
                    async for message in session.prompt(
                        prompt_str,
                        merge_wire_messages=True,
                    ):
                        print_agent_json(lambda: message.model_dump_json())

                except Exception as e:
                    import time
                    if "429" in str(e):
                        wait_time = 4 ** attempt  # 1, 4, 16, 64, 128 秒
                        print_warning(f"Rate limited. Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                break
        finally:
            if create_session:
                await session.close()
                del session
    asyncio.run(func())
    if create_session:
        print_success('Finished')
    else:
        _print_usage(session)


def prompt_path(path: Path, split_word: str = None, session=None):
    f = open(path, 'r', encoding='utf-8')
    if not f:
        print_error(f'File {str(path)} not found.')
        return
    s = f.read()
    f.close()
    if split_word:
        words = s.strip().split(split_word)
        for i in words:
            prompt(i, session=session)
    else:
        prompt(s, session=session)


def fix_error(
        command: str,
        extra_prompt: str = None,
        skip_success: bool = True,
        keycode: tuple = ('error'),
        session=None,
        create_session: bool = False):
    result = _run_process_with_error(
        command, keycode, skip_success=skip_success)
    if result is None:
        print_success('No error.')
        return True
    error_keyword = None
    for i in keycode:
        if error_keyword:
            error_keyword += ', ' + i
        else:
            error_keyword = i
    prompt_str = f'Fix "{error_keyword}" from command {command}:\n{result}\n'
    if extra_prompt is not None:
        prompt_str = f'{extra_prompt}, {prompt_str}'

    prompt(prompt_str, session, create_session)
    return False


def async_prompt(prompt_str: str, session=None):
    return run_thread(prompt, (prompt_str, session, True))


def async_fix_error(
    command: str,
    extra_prompt: str = None,
    skip_success: bool = True,
    keycode: tuple = ('error',),
    session=None
):
    return run_thread(fix_error, (command, extra_prompt, skip_success, keycode, session, True))


def read_file(path: Path, split_word: str = None):
    path = Path(path)
    if not path.exists():
        return ''
    f = open(path, 'r', encoding='utf-8')
    s = f.read()
    f.close()
    if split_word:
        return s.split(split_word)
    return s
