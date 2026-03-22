from agent_utils import *
from agent_utils import _run_process_with_error, _percentage_str
from kaos.path import KaosPath
import asyncio
import time
from pathlib import Path

_default_session = None
_ralph_iterations = 0
_default_thinking = False
_default_yolo = True
_default_agent_file = Path(__file__).parent / 'agent.yaml'
_default_work_dir = KaosPath(os.curdir)
_default_skill_dir = None
__env_initialized = False


def _init_model():
    def _check_legal(value, start_with):
        if value is None or type(value) != str:
            return False
        return value.startswith(start_with)

    global __env_initialized
    if __env_initialized:
        return
    __env_initialized = True
    api_key = os.environ.get("KIMI_API_KEY")
    if not _check_legal(api_key, 'sk'):
        print_error('API key shoud be setted to KIMI_API_KEY environment var')
        exit(1)

    if not _check_legal(os.environ.get("KIMI_BASE_URL"), 'http'):
        os.environ["KIMI_BASE_URL"] = "https://api.kimi.com/coding/v1"
    default_model = 'kimi-for-coding'
    config_model = os.environ.get("KIMI_MODEL_NAME")
    if not _check_legal(config_model, 'kimi'):
        os.environ['KIMI_MODEL_NAME'] = default_model
    elif config_model != default_model:
        default_model = config_model
        print_debug(f'Using {config_model} model.')


def _get_skill_dir():
    global _default_skill_dir
    if _default_skill_dir:
        if type(_default_skill_dir) is not KaosPath:
            _default_skill_dir = KaosPath(_default_skill_dir)
        return _default_skill_dir
    def _gen():
        d = _default_skill_dir
        if d is not None:
            return d
        d = Path(os.curdir) / ".agents/skills"
        if d.exists():
            return d
        d = Path(os.curdir) / ".opencode/skills"
        if d.exists():
            return d
        d = Path(os.curdir) / ".config/.agents/skills"
        if d.exists():
            return d
        return None
    _default_skill_dir = _gen()
    if _default_skill_dir:
        print_info(f'skill dir: {str(_default_skill_dir)}')
        if type(_default_skill_dir) is not KaosPath:
            _default_skill_dir = KaosPath(_default_skill_dir)
        return _default_skill_dir
    return None


def _create_config():
    _init_model()
    from kimi_agent_sdk import Config
    from kimi_cli.config import LoopControl
    cfg = Config()
    if not cfg.loop_control:
        cfg.loop_control = LoopControl()
    return cfg


def context_path() -> Path:
    user_home = Path.home()
    return user_home / '.kimi' / 'sessions'


def delete_session_dir() -> Path:
    import shutil
    path = context_path()
    if path.exists():
        shutil.rmtree(path)
        print_success(f'{str(path)} deleted.')


_session_idx = 0


async def _create_session_async(
    session_id: str = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[bool] = None,
    ralph_loop: Optional[bool] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[bool] = None,
    resume=False
):
    global _session_idx
    if session_id is None:
        session_id = str(_session_idx)
        _session_idx += 1
    cfg = _create_config()

    # No ralph mode defaultly, manually do validate please
    cfg.loop_control.max_ralph_iterations = _ralph_iterations
    if _ralph_iterations != 0:
        cfg.loop_control.max_steps_per_turn = 10000
        cfg.loop_control.reserved_context_size = 48_000
    else:
        cfg.loop_control.reserved_context_size = 32_000
    # custom config
    if ralph_loop is not None and ralph_loop != (_ralph_iterations != 0):
        cfg.loop_control.max_ralph_iterations = -1 if ralph_loop else 0

    from kimi_agent_sdk import Session
    session = None
    if resume:
        session = await Session.resume(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else _default_work_dir,
            skills_dir=skills_dir if skills_dir is not None else _get_skill_dir(),
            yolo=yolo if yolo is not None else _default_yolo,
            thinking=thinking if thinking is not None else _default_thinking,
            config=cfg,
            agent_file=agent_file if agent_file is not None else _default_agent_file
        )
        if not session:
            print_warning(f'Session {session_id} not found.')
    if not session:
        session = await Session.create(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else _default_work_dir,
            skills_dir=skills_dir if skills_dir is not None else _get_skill_dir(),
            yolo=yolo if yolo is not None else _default_yolo,
            thinking=thinking if thinking is not None else _default_thinking,
            config=cfg,
            agent_file=agent_file if agent_file is not None else _default_agent_file
        )
    return session


def create_session(
    session_id: str = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[bool] = None,
    ralph_loop: Optional[bool] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[bool] = None,
    resume=False
):

    return asyncio.run(_create_session_async(
        session_id,
        work_dir,
        skills_dir,
        ralph_loop,
        thinking,
        yolo,
        agent_file,
        resume
    ))


def close_session(session):
    asyncio.run(session.close())


def get_default_session():
    global _default_session
    return _default_session


def _create_default_session(resume: bool = True):
    global _default_session
    if _default_session:
        return _default_session
    _default_session = create_session("default", resume=resume)
    return _default_session


_should_print_usage = threading.local()
_should_print_usage.value = True


def _print_usage(session):
    if not getattr(_should_print_usage, 'value', False):
        return
    s = _percentage_str(session.status.context_usage)
    print_success(
        f'Finished, context usage: {s}'
    )


def print_usage(session=None):
    if not session:
        session = _create_default_session()
    s = _percentage_str(session.status.context_usage)
    print_success(
        f'Context usage: {s}'
    )


def clear_context(force_create: bool = False):
    global _default_session
    if _default_session:
        if not force_create and _default_session.status.context_usage < 1e-8:
            _print_usage(_default_session)
            return
        elif _default_session is not None:
            asyncio.run(_default_session.close())
        _default_session = None
    _create_default_session(False)
    _print_usage(_default_session)




def prompt(prompt_str: str, session=None):
    import my_tools.todo as todo
    _temp_create_session = False
    if session is None:
        session = get_default_session()
    elif session == False:
        session = create_session()
        _temp_create_session = True
    todo.set_current_id(str(session.id))

    global _default_session
    prompt_str = prompt_str.strip()

    async def func():
        nonlocal session, _temp_create_session
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
                _print_usage(session)
                max_retries = 0
            except Exception as e:
                print_error(str(e))
                import time
                if "429" in str(e):
                    wait_time = 4 ** attempt  # 1, 4, 16, 64, 128 秒
                    print_warning(f"Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif attempt == max_retries - 1:
                    raise
                else:
                    time.sleep(1)
            finally:
                if _temp_create_session:
                    await session.close()
            break
    asyncio.run(func())


def validate(
    prompt_str: Optional[str], session=None
):
    if type(prompt_str) == str and len(prompt_str) > 0:
        import my_tools.flag as flag
        flag.reset_flag()
        prompt_str = prompt_str + \
            '\n\nIf the condition is true, call tool:SetFlag.'
        prompt(prompt_str, session)
        return flag.check_flag()
    else:
        return prompt_str == True


def make_todo(
    prompt_str: Optional[str], session=None
):
    import my_tools.todo as todo
    todo._todo_called = False
    prompt_str = prompt_str + '\n\ncall tool:SetTodoList, to make a todo.'
    prompt(prompt_str, session)
    return todo._todo_called


def get_todo(
    session=None
):
    import my_tools.todo as todo
    return todo.get_todo_list(str(session.id) if session is not None else 'default')


def clear_todo(
    session=None
):
    import my_tools.todo as todo
    return todo.clear_todo_list(str(session.id) if session is not None else 'default')


def update_todo_status(
    session=None,
    indices_str: str = '',
    status: str = 'done'
):
    """Update the status of todo items by indices.

    Args:
        session: The session object
        indices_str: Comma-separated indices or range (e.g., '1,2,3' or '1-3')
        status: The new status ('pending', 'in_progress', or 'done')
    """
    import my_tools.todo as todo
    from agent_utils import print_success, print_error, print_info

    result = todo.get_todo_list(
        str(session.id) if session is not None else 'default')
    if not result:
        print_info('No todo items found.')
        return

    todos = result.todos if hasattr(result, 'todos') else []
    if not todos:
        print_info('No todo items found.')
        return

    # Parse indices
    indices = set()
    if not indices_str:
        # If no indices specified, update all items
        indices = set(range(len(todos)))
    else:
        parts = indices_str.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Range like '1-3'
                try:
                    start, end = part.split('-', 1)
                    start_idx = int(start.strip()) - 1  # Convert to 0-based
                    end_idx = int(end.strip()) - 1
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(todos):
                            indices.add(i)
                except ValueError:
                    print_error(f'Invalid range: {part}')
                    return
            else:
                # Single index
                try:
                    idx = int(part) - 1  # Convert to 0-based
                    if 0 <= idx < len(todos):
                        indices.add(idx)
                except ValueError:
                    print_error(f'Invalid index: {part}')
                    return

    if not indices:
        print_info('No valid indices specified.')
        return

    # Update the status of specified items
    updated_count = 0
    for idx in sorted(indices):
        todo_item = todos[idx]
        if hasattr(todo_item, 'status'):
            old_status = todo_item.status
            todo_item.status = status
        else:
            old_status = todo_item.get('status', 'pending')
            todo_item['status'] = status
        updated_count += 1
        title = todo_item.title if hasattr(
            todo_item, 'title') else todo_item.get('title', 'Unknown')
        print_success(f'Updated: "{title}" [{old_status} -> {status}]')

    # Save the updated todo list
    todo.set_todo_list(
        session.id if session is not None else 'default', result)

    print_success(f'Updated {updated_count} item(s) to "{status}".')


def prompt_path(path: Path, split_word: str = None, session=None, after_prompt_coro=None):
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


def fix_error(
        command: str,
        extra_prompt: str = None,
        skip_success: bool = True,
        keycode: tuple = ('error', ),
        session=None,
        max_loop=4):
    for i in range(max_loop):
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

        prompt(prompt_str, session)
    return False


def async_prompt(prompt_str: str, session=False):  # make session false, default stateless
    return run_thread(prompt, (prompt_str, session))


def async_fix_error(
    command: str,
    extra_prompt: str = None,
    skip_success: bool = True,
    keycode: tuple = ('error',),
    session=False
):
    return run_thread(fix_error, (command, extra_prompt, skip_success, keycode, session))


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
