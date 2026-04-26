from typing import Optional
from pathlib import Path
import kimix.base as base
from . import _globals
from .session import clear_default_context

def set_plan_mode(value: bool = True, resume: bool = True) -> None:
    base._default_plan_mode = value == True
    if not _globals._default_session:
        return
    clear_default_context(True, resume)
