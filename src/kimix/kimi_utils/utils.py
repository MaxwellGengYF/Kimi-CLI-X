from typing import Optional
from pathlib import Path
import kimix.agent_utils as agent_utils
from . import _globals
from .session import clear_context


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
    if not _globals._default_session:
        return
    clear_context(True, resume)
