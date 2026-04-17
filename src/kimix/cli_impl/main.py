from . import constants
from .core import _run_cli
from kimix.kimi_utils import delete_session_dir


def cli():
    try:
        _run_cli()
    finally:
        if constants.CLEAN_MODE:
            delete_session_dir()
