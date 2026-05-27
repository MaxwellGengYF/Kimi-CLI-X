#!/usr/bin/env python3
"""Run syntax_check.py on all Python files under the project in parallel."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SYNTAX_CHECK_SCRIPT = PROJECT_ROOT / "tools" / "syntax_check.py"
RESULT_FILE = PROJECT_ROOT / "check_result.txt"

# Directories to skip
SKIP_DIRS = {
    "__pycache__",
    ".venv",
    ".git",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "build",
    "dist",
    ".eggs",
    "*.egg-info",
}


def is_skipped(path: Path) -> bool:
    """Return True if any part of the path matches a skip directory."""
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False


def collect_python_files(root: Path) -> list[Path]:
    """Recursively collect all *.py files under root, excluding skipped dirs."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                fpath = Path(dirpath) / fname
                if not is_skipped(fpath):
                    files.append(fpath)
    return files


def check_file(py_file: Path) -> tuple[Path, int, str, str]:
    """Run syntax_check.py on a single file. Returns (file, returncode, stdout, stderr)."""
    cmd = [sys.executable, str(SYNTAX_CHECK_SCRIPT), str(py_file)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return py_file, result.returncode, result.stdout, result.stderr


def main() -> int:
    print("Collecting Python files ...")
    py_files = collect_python_files(PROJECT_ROOT)
    print(f"Found {len(py_files)} Python files.")

    errors: list[tuple[Path, str, str]] = []
    warnings: list[tuple[Path, str, str]] = []
    ok_count = 0

    # Run checks in parallel with at most 32 threads
    max_workers = min(32, len(py_files)) if py_files else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(check_file, f): f for f in py_files
        }
        for future in as_completed(future_to_file):
            py_file, rc, stdout, stderr = future.result()
            if rc != 0:
                errors.append((py_file, stdout, stderr))
            elif stderr.strip():
                # Non-zero stderr but zero returncode counts as warning
                warnings.append((py_file, stdout, stderr))
            else:
                ok_count += 1

    # Format results
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("Syntax Check Report")
    lines.append("=" * 70)
    lines.append(f"Total files checked: {len(py_files)}")
    lines.append(f"Passed:              {ok_count}")
    lines.append(f"Warnings:            {len(warnings)}")
    lines.append(f"Errors:              {len(errors)}")
    lines.append("")

    if errors:
        lines.append("-" * 70)
        lines.append("ERRORS")
        lines.append("-" * 70)
        for py_file, stdout, stderr in errors:
            lines.append(f"\nFile: {py_file}")
            if stdout.strip():
                lines.append("[stdout]")
                lines.append(stdout)
            if stderr.strip():
                lines.append("[stderr]")
                lines.append(stderr)
        lines.append("")

    if warnings:
        lines.append("-" * 70)
        lines.append("WARNINGS")
        lines.append("-" * 70)
        for py_file, stdout, stderr in warnings:
            lines.append(f"\nFile: {py_file}")
            if stdout.strip():
                lines.append("[stdout]")
                lines.append(stdout)
            if stderr.strip():
                lines.append("[stderr]")
                lines.append(stderr)
        lines.append("")

    lines.append("=" * 70)
    lines.append("Done")
    lines.append("=" * 70)

    report = "\n".join(lines)
    RESULT_FILE.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nReport saved to: {RESULT_FILE}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
