#!/usr/bin/env python3
"""Python syntax/type check CLI using mypy."""

import argparse
import orjson
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Python file syntax and types using mypy.")
    parser.add_argument("file_path", help="Path to the Python file to validate.")
    parser.add_argument("--project-root", default=".", help="Root directory of the project for mypy config discovery.")
    parser.add_argument("--verbose", action="store_true", help="Include verbose mypy output.")
    args = parser.parse_args()

    file_path = Path(args.file_path)

    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 2

    ext = file_path.suffix.lower()
    if ext != ".py":
        print(f"Unsupported file extension: {ext}. Only .py files are supported.", file=sys.stderr)
        return 2

    project_root = Path(args.project_root).resolve()

    # Build mypy command
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        str(file_path),
        "--output",
        "json",
    ]
    if args.verbose:
        cmd.append("--verbose")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
    except Exception as e:
        print(f"Failed to run mypy: {e}", file=sys.stderr)
        return 2

    # Parse mypy JSON output
    diagnostics = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            diag = orjson.loads(line)
            diagnostics.append(diag)
        except orjson.JSONDecodeError:
            continue

    # Also capture stderr if any
    stderr_lines = [
        stripped
        for line in result.stderr.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("LOG:")
    ]

    if not diagnostics and result.returncode == 0:
        output = f"No issues found in {file_path.name}."
        if args.verbose:
            output += f"\nProject root: {project_root}"
        print(output)
        return 0

    # Format diagnostics
    errors = 0
    warnings = 0
    notes = 0

    for diag in diagnostics:
        severity = diag.get("severity", "error")
        msg = f"{severity.capitalize()}: {diag.get('message', '')}"
        if diag.get("code"):
            msg += f" [{diag['code']}]"
        msg += f" at line {diag.get('line', 0)}, col {diag.get('column', 0)}"
        print(msg)

        if severity == "error":
            errors += 1
        elif severity == "warning":
            warnings += 1
        else:
            notes += 1

    if stderr_lines:
        print("\nAdditional output:")
        for sl in stderr_lines:
            print(f"  {sl}")

    summary = f"\n{'-' * 60}\nTotal: {errors} error(s), {warnings} warning(s), {notes} note(s)"
    print(summary)

    if args.verbose:
        print(f"Project root: {project_root}")

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
