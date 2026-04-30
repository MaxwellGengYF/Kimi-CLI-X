import subprocess
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
def get_uncommitted_diff(filepath: str) -> str:
    """Return the uncommitted diff for a specific file."""
    result = subprocess.run(
        ["git", "diff", "--", filepath],
        capture_output=True,
        text=True,
        check=False,
        errors='replace'
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run tools/git_diff.py <filepath>")
        sys.exit(1)

    target = sys.argv[1]
    try:
        diff = get_uncommitted_diff(target)
        print(diff, end="")
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
