"""Test to run mypy on src/kimix/kimi_utils.py and collect static errors, warnings, hints."""

import logging
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)

if len(sys.argv) <= 1:
    logger.error("No target file provided. Usage: python tools/syntax_check.py <target_file>")
    sys.exit(1)

input_path = Path(sys.argv[1])

if input_path.is_absolute():
    try:
        relative_path = input_path.relative_to(PROJECT_ROOT)
    except ValueError:
        logger.error(
            "Absolute path %s is not within the project directory %s",
            input_path,
            PROJECT_ROOT,
        )
        sys.exit(1)
else:
    relative_path = input_path

TARGET_FILE = PROJECT_ROOT / relative_path


def _run_mypy(*extra_args: str) -> tuple[int, str, str]:
    """Run mypy on the target file and return (returncode, stdout, stderr)."""
    cmd = [
        sys.executable, "-m", "mypy",
        str(TARGET_FILE),
        "--show-error-codes",
        "--show-column-numbers",
        "--no-error-summary",
    ] + list(extra_args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def mypy_results() -> tuple[int, str, str]:
    """Run mypy once and share parsed results across the class."""
    returncode, stdout, stderr = _run_mypy()
    return returncode, stdout, stderr


if __name__ == '__main__':
    returncode, stdout, stderr = mypy_results()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    exit(returncode)
