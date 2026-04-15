from agent_utils import *
from agent_utils import _run_process_with_error, _percentage_str
from kaos.path import KaosPath
import asyncio
import time
from pathlib import Path
import agent_utils
from typing import Callable, List, Optional
from collections import OrderedDict
import hashlib
from string import Template
from kimi_cli.soul.agent import BuiltinSystemPromptArgs

# Import TextSearchIndex for RAG functionality
from my_tools.skill.faiss.text_search import TextSearchIndex, SearchResult
_default_session = None
__env_initialized = False

# RAG index cache (LRU cache with max size of 3)
_index_cache: OrderedDict[str, TextSearchIndex] = OrderedDict()
_MAX_INDEX_CACHE_SIZE: int = 3


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


def make_kaos_dir(obj: object) -> KaosPath:
    if type(obj) is not KaosPath:
        return KaosPath(obj)
    return obj


def _ensure_skill_dirs(skill_dirs: object) -> list[KaosPath]:
    from collections.abc import Iterable
    if skill_dirs is None:
        return []
    if type(skill_dirs) == list:
        return make_kaos_dir(skill_dirs)
    if isinstance(skill_dirs, Iterable) and not isinstance(skill_dirs, (str, bytes)):
        return [make_kaos_dir(i) for i in skill_dirs]
    return [make_kaos_dir(skill_dirs)]
_SYSTEM_PROMP = Template('''You are a coding agent.
Rules:
1. Minimal diff; preserve surrounding formatting.
2. No explanations, apologies, or questions.
3. For long tasks, use `Run`/`Python` with `run_in_background=true`, then manage via `TaskList`, `TaskOutput`, `Input`, `TaskStop`. Return control immediately after starting.
${SHELL}${PLAN_MODE}
${AGENTS_MD}${SKILLS}
''')

def get_system_prompt(
    plan_mode: bool | None = None,
    work_dir: Optional[KaosPath] = None):
    agent_md = (Path(str(work_dir)) if work_dir is not None else Path(os.curdir)) / 'AGENTS.md'
    plan_mode = plan_mode if plan_mode is not None else agent_utils._default_plan_mode
    def system_prompt_func(args: BuiltinSystemPromptArgs) -> str:
        plan_mode_doc = None
        shell_doc = None
        agent_md_doc = None
        skill_doc = None
        if args.KIMI_OS == 'Windows':
            shell_doc = '''
4. No Shell commands; use `Run`/`Python` instead.
'''
        else:
            shell_doc = f'''
4. Shell: {args.KIMI_SHELL} 
'''
        if plan_mode:
           plan_mode_doc = f'''
5. Plan mode: draft plan, run `ExitPlanMode`, then execute.
'''
        if agent_md.is_file():
            agent_md_doc = agent_md.read_text(encoding='utf-8', errors='replace')
            agent_md_doc = f'''
AGENTS.md:
```
{agent_md_doc}
```
'''
        if args.KIMI_SKILLS and args.KIMI_SHELL.lower() != 'no skills found.':
            skill_doc= f'''
Skills:
{args.KIMI_SKILLS}
'''
        return _SYSTEM_PROMP.substitute(
            PLAN_MODE=(plan_mode_doc.strip() + '\n') if plan_mode_doc else '',
            SHELL=(shell_doc.strip() + '\n') if shell_doc else '',
            AGENTS_MD=(agent_md_doc.strip() + '\n') if agent_md_doc else '',
            SKILLS=(skill_doc.strip() + '\n') if skill_doc else '',
            ).strip()
    return system_prompt_func
    

async def _create_session_async(
    session_id: str = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[KaosPath] = None,
    ralph_loop: Optional[bool] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[Path] = None,
    resume=False,
    plan_mode: Optional[bool] = None
):
    global _session_idx
    if session_id is None:
        session_id = str(_session_idx)
        _session_idx += 1
    tool_call_failed_list = list()
    agent_utils._tool_call_failed_lists[session_id] = tool_call_failed_list
    cfg = _create_config()

    # No ralph mode defaultly, manually do validate please
    cfg.loop_control.max_ralph_iterations = agent_utils._ralph_iterations
    cfg.loop_control.max_steps_per_turn = 10000
    # custom config
    if ralph_loop is not None:
        cfg.loop_control.max_ralph_iterations = -1 if ralph_loop else 0

    from kimi_agent_sdk import Session
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
                skills_dir) if skills_dir is not None else agent_utils._get_skill_dirs(),
            yolo=yolo if yolo is not None else agent_utils._default_yolo,
            plan_mode=plan_mode if plan_mode is not None else agent_utils._default_plan_mode,
            thinking=thinking if thinking is not None else agent_utils._default_thinking,
            config=cfg,
            agent_file=agent_file,
            tool_call_failed_list=tool_call_failed_list,
            custom_system_prompt=get_system_prompt(plan_mode, work_dir),
        )
        if not session:
            print_debug(f'Session {session_id} not found.')
    if not session:
        session = await Session.create(
            session_id=session_id,
            work_dir=work_dir if work_dir is not None else KaosPath(os.curdir),
            skills_dirs=_ensure_skill_dirs(
                skills_dir) if skills_dir is not None else agent_utils._get_skill_dirs(),
            yolo=yolo if yolo is not None else agent_utils._default_yolo,
            plan_mode=plan_mode if plan_mode is not None else agent_utils._default_plan_mode,
            thinking=thinking if thinking is not None else agent_utils._default_thinking,
            config=cfg,
            agent_file=agent_file,
            tool_call_failed_list=tool_call_failed_list,
            custom_system_prompt=get_system_prompt(plan_mode, work_dir),
        )
    return session


def create_session(
    session_id: str = None,
    work_dir: Optional[KaosPath] = None,
    skills_dir: Optional[KaosPath] = None,
    ralph_loop: Optional[bool] = None,
    thinking: Optional[bool] = None,
    yolo: Optional[bool] = None,
    agent_file: Optional[Path] = None,
    resume=False,
    plan_mode: Optional[bool] = None
):
    return asyncio.run(_create_session_async(
        session_id,
        work_dir,
        skills_dir,
        ralph_loop,
        thinking,
        yolo,
        agent_file,
        resume,
        plan_mode
    ))


def get_tool_call_errors(session=None):
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


def close_session(session):
    if not session:
        return
    try:
        del agent_utils._tool_call_failed_lists[session.id]
    except:
        pass
    asyncio.run(session.close())


async def close_session_async(session):
    if not session:
        return
    try:
        del agent_utils._tool_call_failed_lists[session.id]
    except:
        pass
    await session.close()


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


def clear_context(force_create: bool = False, resume: bool = False, print_info: bool = True):
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
    session=None,
    # settings
    read_agents_md: bool = False,
    skill_name: str | None = None,
    output_function: Callable | None = None,
    info_print: bool = True
):
    _temp_create_session = False
    if session is None:
        session = get_default_session()
    elif session == False:
        session = await _create_session_async()
        _temp_create_session = True
    prompt_str = prompt_str.strip()

    def enable_skill(skill_name):
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
        try:
            async for message in session.prompt(
                prompt_str,
                merge_wire_messages=True,
            ):
                print_agent_json(
                    lambda: message.model_dump_json(), output_function)
            if info_print:
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


def prompt(
    prompt_str: str,
    session=None,
    # settings
    read_agents_md: bool = False,
    skill_name: str | None = None,
    output_function: Callable | None = None,
    info_print: bool = True
):
    asyncio.run(
        prompt_async(
            prompt_str,
            session,
            # settings
            read_agents_md,
            skill_name,
            output_function,
            info_print
        ))


def validate(
    prompt_str: Optional[str], session=None
):
    if type(prompt_str) == str and len(prompt_str) > 0:
        import my_tools.flag as flag
        flag.reset_flag()
        prompt_str = prompt_str + \
            '\n\nIf the condition is true, run `Setflag` tool.'
        prompt(prompt_str, session)
        return flag.check_flag() is not None
    else:
        return False


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
        if i == 0 and result is None:
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
        from my_tools.common import _maybe_export_output
        prompt(_maybe_export_output(prompt_str), session)
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


def set_plan_mode(value: bool = True):
    agent_utils._default_plan_mode = value == True
    if not _default_session:
        return
    clear_context(True, True)


def rag(
    query: str,
    file_path: Optional[str | Path] = None,
    top_k: int = 5,
    content: bool = False,
    refresh: bool = False,
    hybrid_search: bool = True,
    negative: Optional[str] = None
) -> List[SearchResult]:
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

    if TextSearchIndex is None:
        print_warning(
            "TextSearchIndex not available. Please check dependencies.")
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
        index = TextSearchIndex(cache_dir=cache_dir, lazy_load=True)
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
