from kimix.agent_utils import *
from kimix.agent_utils import run_process_with_error, percentage_str
from kaos.path import KaosPath
import asyncio
from pathlib import Path
import kimix.agent_utils as agent_utils
from typing import Callable, List, Optional
from collections import OrderedDict
import hashlib
from string import Template
from kimi_cli.soul.agent import BuiltinSystemPromptArgs
from typing import Any
import os
import threading
# TextSearchIndex and SearchResult are lazily imported to avoid hard faiss dependency
from kimi_agent_sdk import Session
TextSearchIndex = None
SearchResult = None


def _ensure_text_search() -> tuple[Any, Any]:
    """Lazy import of TextSearchIndex and SearchResult."""
    global TextSearchIndex, SearchResult
    if TextSearchIndex is None:
        from my_tools.skill.faiss.text_search import TextSearchIndex as _TSI, SearchResult as _SR
        TextSearchIndex = _TSI
        SearchResult = _SR
    return TextSearchIndex, SearchResult


_default_session: Session | None = None
__env_initialized = False

# RAG index cache (LRU cache with max size of 3)
_index_cache: OrderedDict[Any, Any] = OrderedDict()
_MAX_INDEX_CACHE_SIZE: int = 3


def _init_model(check_config: bool) -> None:
    def _check_legal(value: str | None, start_with: str) -> bool:
        if value is None or type(value) != str:
            return False
        return value.startswith(start_with)

    global __env_initialized
    if __env_initialized:
        return
    __env_initialized = True
    if check_config:
        api_key = os.environ.get("KIMI_API_KEY")
        if not _check_legal(api_key, 'sk'):
            print_error('KIMI_API_KEY not found.')
            exit(1)

        if not _check_legal(os.environ.get("KIMI_BASE_URL"), 'http'):
            os.environ["KIMI_BASE_URL"] = "https://api.kimi.com/coding/v1"
        default_model = 'kimi-for-coding'
        config_model = os.environ.get("KIMI_MODEL_NAME")
        if not _check_legal(config_model, 'kimi'):
            os.environ['KIMI_MODEL_NAME'] = default_model
        elif config_model is not None and config_model != default_model:
            default_model = config_model
            print_debug(f'Using {config_model} model.')


def _create_config(provider_dict: dict[str, Any] | None = None) -> Any:
    provider_dict = provider_dict if provider_dict is not None else agent_utils._default_provider
    _init_model(provider_dict is None)
    from kimi_agent_sdk import Config
    from kimi_cli.config import LoopControl
    cfg = Config()
    # DO THIS: support other providers and models
    from kimi_cli.config import LLMModel, LLMProvider
    if provider_dict is not None:
        model_name = provider_dict.get('model_name', 'unknown_model')
        name = provider_dict.get('name', 'unknown')
        print_debug(f'Using model `{model_name}` from provider `{name}`')
        model = provider_dict.get('model')
        max_context_size = provider_dict.get('max_context_size')
        capabilities = provider_dict.get('capabilities', [])
        url = provider_dict.get('url')
        provider_type = provider_dict.get("type")
        assert provider_type is not None, "`provider_type` must be provided in  config"
        assert max_context_size is not None, "`max_context_size` must be provided in  config"
        assert model is not None, "model must be provided in config"
        assert url is not None, "url must be provided in config"
        provider = LLMProvider(
            type=provider_type,
            # example: "https://api.minimaxi.com/anthropic"
            base_url=url,
            # TODO: delete this before push.
            api_key=provider_dict.get('api_key', ''),
            custom_headers=provider_dict.get('custom_headers'),
            oauth=provider_dict.get('oauth'),
        )
        cfg.default_model = model_name
        cfg.models = {
            model_name: LLMModel(
                provider=name, model=model, max_context_size=max_context_size, capabilities=capabilities)
        }
        cfg.providers = {
            name: provider
        }
    if not cfg.loop_control:
        cfg.loop_control = LoopControl()
    return cfg


def context_path() -> Path:
    user_home = Path.home()
    return user_home / '.kimi' / 'sessions'


def delete_session_dir() -> None:
    import shutil
    path = context_path()
    if path.exists():
        shutil.rmtree(path)
        print_success(f'{str(path)} deleted.')


_session_idx = 0


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


_SYSTEM_PROMP = Template('''You are a coding agent.
Rules:
1. Minimal diff; preserve surrounding formatting.
2. No explanations, apologies, or questions.
3. For long tasks, use `Run`/`Python` with `run_in_background=true`, then manage via `TaskList`, `TaskOutput`, `Input`, `TaskStop`. Return control immediately after starting.
4. Python path `${PYTHON_PATH}`, ALWAYS use this python.
5. For complex or multi-step tasks, use `SetTodoList` to track progress.
${SHELL}${PLAN_MODE}${YOLO_MODE}
${AGENTS_MD}${SKILLS}
''')


def get_system_prompt(
        plan_mode: bool | None = None,
        yolo: bool | None = None,
        work_dir: Optional[KaosPath] = None) -> Callable[[BuiltinSystemPromptArgs], str]:
    agent_md = (Path(str(work_dir)) if work_dir is not None else Path(
        os.curdir)) / 'AGENTS.md'
    plan_mode = plan_mode if plan_mode is not None else agent_utils._default_plan_mode
    yolo = yolo if yolo is not None else agent_utils._default_yolo

    def system_prompt_func(args: BuiltinSystemPromptArgs) -> str:
        plan_mode_doc = None
        shell_doc = None
        agent_md_doc = None
        skill_doc = None
        yolo_doc = None
        index = 6
        if args.KIMI_OS == 'Windows':
            shell_doc = f'''
{index}. No Shell commands; use `Run`/`Python` instead.
'''
        else:
            shell_doc = f'''
{index}. Shell: {args.KIMI_SHELL} 
'''
        index += 1
        if plan_mode:
            plan_mode_doc = f'''
{index}. Plan mode: draft plan, run `ExitPlanMode`, then execute.
'''
            index += 1
        if yolo:
            yolo_doc = f'''
{index}. Yolo mode: act decisively without asking. Never write outside working directory or change system settings(if not asked).
'''
            index += 1
        if agent_md.is_file():
            agent_md_doc = agent_md.read_text(
                encoding='utf-8', errors='replace')
            agent_md_doc = f'''
AGENTS.md:
```
{agent_md_doc}
```
'''
        if args.KIMI_SKILLS and args.KIMI_SHELL.lower() != 'no skills found.':
            skill_doc = f'''
Skills:
{args.KIMI_SKILLS}
'''
        return _SYSTEM_PROMP.substitute(
            PYTHON_PATH=sys.executable,
            PLAN_MODE=(plan_mode_doc.strip() + '\n') if plan_mode_doc else '',
            SHELL=shell_doc.strip() + '\n',
            AGENTS_MD=(agent_md_doc.strip() + '\n') if agent_md_doc else '',
            SKILLS=(skill_doc.strip() + '\n') if skill_doc else '',
            YOLO_MODE=(yolo_doc.strip() + '\n') if yolo_doc else '',
        ).strip()
    return system_prompt_func


async def _create_session_async(
    session_id: Optional[str] = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[KaosPath] = None,
    ralph_loop: Optional[bool] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[Path] = None,
    resume: bool = False,
    plan_mode: Optional[bool] = None,
    provider_dict: dict[str, Any] | None = None,
) -> Session:
    global _session_idx
    if session_id is None:
        session_id = str(_session_idx)
        _session_idx += 1
    tool_call_failed_list: list[Any] = list()
    agent_utils._tool_call_failed_lists[session_id] = tool_call_failed_list
    cfg = _create_config(provider_dict)

    # No ralph mode defaultly, manually do validate please
    cfg.loop_control.max_ralph_iterations = agent_utils._ralph_iterations
    cfg.loop_control.max_steps_per_turn = 10000
    # custom config
    if ralph_loop is not None:
        cfg.loop_control.max_ralph_iterations = -1 if ralph_loop else 0

    session = None
    if agent_file is None:
        agent_file = agent_utils._default_agent_file
    else:
        if type(agent_file) is not Path:
            agent_file = Path(agent_file)
        if not agent_file.is_absolute():
            agent_file = Path(__file__).parent / agent_file
    if resume:
        session = await Session.resume(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else KaosPath(os.curdir),
            skills_dirs=_ensure_skill_dirs(
                skills_dir) if skills_dir is not None else agent_utils.get_skill_dirs(),
            yolo=yolo if yolo is not None else agent_utils._default_yolo,
            plan_mode=plan_mode if plan_mode is not None else agent_utils._default_plan_mode,
            thinking=thinking if thinking is not None else agent_utils._default_thinking,
            config=cfg,
            agent_file=agent_file,
            tool_call_failed_list=tool_call_failed_list,
            custom_system_prompt=get_system_prompt(plan_mode, yolo, work_dir),
        )
        if not session:
            print_debug(f'Session {session_id} not found.')
    if not session:
        session = await Session.create(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else KaosPath(os.curdir),
            skills_dirs=_ensure_skill_dirs(
                skills_dir) if skills_dir is not None else agent_utils.get_skill_dirs(),
            yolo=yolo if yolo is not None else agent_utils._default_yolo,
            plan_mode=plan_mode if plan_mode is not None else agent_utils._default_plan_mode,
            thinking=thinking if thinking is not None else agent_utils._default_thinking,
            config=cfg,
            agent_file=agent_file,
            tool_call_failed_list=tool_call_failed_list,
            custom_system_prompt=get_system_prompt(plan_mode, yolo, work_dir),
        )
    return session


def create_session(
    session_id: Optional[str] = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[KaosPath] = None,
    ralph_loop: Optional[bool] = None,
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
        ralph_loop,
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
    elif type(session) == str:
        id = session
    else:
        id = session.id
    lst = agent_utils._tool_call_failed_lists.get(id, None)
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
        del agent_utils._tool_call_failed_lists[session.id]
    except:
        pass
    asyncio.run(session.close())


async def close_session_async(session: Session) -> None:
    if not session:
        return
    try:
        del agent_utils._tool_call_failed_lists[session.id]
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
    global _default_session
    return _default_session


def _create_default_session(resume: bool = True) -> Session:
    global _default_session
    if _default_session:
        return _default_session
    _default_session = create_session("default", resume=resume)
    return _default_session


_should_print_usage = threading.local()
_should_print_usage.value = True


def _print_usage(session: Session) -> None:
    if not getattr(_should_print_usage, 'value', False):
        return
    s = percentage_str(session.status.context_usage)
    print_success(
        f'Finished, context usage: {s}'
    )


def print_usage(session: Session | None = None) -> None:
    if not session:
        session = _create_default_session()
    s = percentage_str(session.status.context_usage)
    print_success(
        f'Context usage: {s}'
    )


def clear_context(force_create: bool = False, resume: bool = False, print_info: bool = True) -> None:
    global _default_session
    if _default_session:
        if not force_create and _default_session.status.context_usage < 1e-8:
            if print_info:
                _print_usage(_default_session)
            return
        elif _default_session is not None:
            asyncio.run(_default_session.close())
        _default_session = None
    _create_default_session(resume)
    if print_info:
        _print_usage(_default_session)


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
        session = get_default_session()
        close_session_after_prompt = False
    prompt_str = prompt_str.strip()
    try:
        def enable_skill(skill_name: str) -> None:
            nonlocal prompt_str
            if not agent_utils._default_skill_dirs:
                print_warning('Skill dir not setted.')
            else:
                skill_found = False
                for skill_dir in agent_utils._default_skill_dirs:
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

        global _default_session
        if info_print:
            print_debug(f'Start...', end='\n\n')

        max_retries = 5
        for attempt in range(max_retries):
            # already canceled.
            if session._cancel_event is not None and session._cancel_event.is_set():
                break
            try:
                async for message in session.prompt(
                    prompt_str,
                    merge_wire_messages=True,
                ):
                    if cancel_callable is not None and cancel_callable():
                        session.cancel()
                        break
                    print_agent_json(
                        lambda: message.model_dump_json(), output_function)
                if info_print:
                    _print_usage(session)
                max_retries = 0
            except KeyboardInterrupt as e:
                if session:
                    session.cancel()
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
            break
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
    output_function: Callable[[Any], Any] | None = None,
    info_print: bool = True,
    cancel_callable: Callable[[], bool] | None = None,
) -> Any:
    session_created = None
    if session is None:
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


def read_file(path: Path | str, split_word: Optional[str] = None) -> str | list[str]:
    path = Path(path)
    if not path.exists():
        return ''
    f = open(path, 'r', encoding='utf-8')
    s = f.read()
    f.close()
    if split_word:
        return s.split(split_word)
    return s


def set_plan_mode(value: bool = True, resume: bool = True) -> None:
    agent_utils._default_plan_mode = value == True
    if not _default_session:
        return
    clear_context(True, resume)


def set_ralph_loop(value: int = -1, resume: bool = True) -> None:
    if value < -1:
        value = -1
    agent_utils._ralph_iterations = value
    if not _default_session:
        return
    clear_context(True, resume)


def rag(
    query: str,
    file_path: Optional[str | Path] = None,
    top_k: int = 5,
    content: bool = False,
    refresh: bool = False,
    hybrid_search: bool = True,
    negative: Optional[str] = None
) -> List[Any]:
    """Perform semantic search using TextSearchIndex.

    This function uses an LRU cache to avoid re-indexing the same paths.

    Args:
        query: Search keywords (keywords only, not sentences)
        file_path: Directory or file path to search within (default: current directory)
        top_k: Number of top results to return (default: 5)
        content: Return full content of matched files (default: False)
        refresh: Force refresh the index (default: False)
        hybrid_search: Enable hybrid search combining semantic and keyword matching (default: True)
        negative: Optional keywords to penalize in search results

    Returns:
        List of SearchResult objects. Returns empty list if TextSearchIndex is not
        available, path does not exist, no documents found, or no results found.
    """
    global _index_cache

    try:
        _TextSearchIndex, _SearchResult = _ensure_text_search()
    except ImportError as e:
        print_warning(f"TextSearchIndex not available: {e}")
        return []

    # Determine the path to search
    search_path = file_path
    if search_path is None:
        search_path = "."

    # Resolve the path
    search_path = str(Path(search_path).resolve())

    # Check if path exists
    if not os.path.exists(search_path):
        print_warning(f"Path does not exist: {file_path}")
        return []

    # Create cache key from path
    normalized = os.path.abspath(search_path)
    cache_key_hash = hashlib.md5(normalized.encode()).hexdigest()[:12]
    index_path = f".index_cache/{cache_key_hash}"
    cache_dir = ".cache/text_search"

    # Use cached index if available and not refreshing (LRU cache)
    index_cache_key = f"{cache_dir}:{index_path}"
    cached = False
    index = None

    if not refresh and index_cache_key in _index_cache:
        # Move to end (most recently used)
        index = _index_cache.pop(index_cache_key)
        _index_cache[index_cache_key] = index
        cached = True
    else:
        # Evict oldest entry if cache is full
        if len(_index_cache) >= _MAX_INDEX_CACHE_SIZE:
            oldest_key, _ = _index_cache.popitem(last=False)
        # Create index with lazy loading and embedding cache
        index = _TextSearchIndex(cache_dir=cache_dir, lazy_load=True)
        _index_cache[index_cache_key] = index

    # Try to load existing index or create new one
    save = False
    if os.path.exists(index_path) and not refresh:
        if not cached:
            index.load(index_path)
        # Remove files that no longer exist
        removed_files = index.remove_missing_files()
        if removed_files:
            save = True

        # Check for new/modified files and update incrementally
        if os.path.isdir(search_path):
            new_files = index.get_new_files(search_path)
            if new_files:
                for file_path_item in new_files:
                    index.add_file(file_path_item)
                save = True
        elif os.path.isfile(search_path):
            if index._is_file_modified(search_path):
                index.add_file(search_path)
                save = True
    else:
        # Fresh indexing (or forced refresh)
        if os.path.isdir(search_path):
            index.add_folder(search_path, parallel=True)
        elif os.path.isfile(search_path):
            index.add_file(search_path)
        # Save the index
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        save = True

    if save:
        index.save(index_path)

    # Check if index is empty
    stats = index.get_stats()
    if stats['total_documents'] == 0:
        print_warning("No documents found to index.")
        return []

    # Perform search based on hybrid_search parameter
    results: list[Any]
    if hybrid_search:
        results = index.hybrid_search(query, top_k=top_k, negative=negative)
    else:
        results = index.search(query, top_k=top_k, negative=negative)

    if not results:
        print_warning(f"No results found for query: '{query}'")
        return []

    # If content flag is True, include full file content in results
    if content:
        for r in results:
            try:
                with open(r.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    r.full_content = f.read()
            except Exception:
                r.full_content = None

    return results
