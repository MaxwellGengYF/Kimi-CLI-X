import subprocess
import sys

def add_and_commit(filepath: str, commit_name: str) -> str:
    """Return the uncommitted diff for a specific file."""
    result = subprocess.run(
        ["git", "add", filepath],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    result = subprocess.run(
        ["git", "commit", "-m", commit_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: uv run tools/git_add.py <filepath> <commit_name>")
        sys.exit(1)

    target = sys.argv[1]
    name = sys.argv[2]
    try:
        diff = add_and_commit(target, name)
        print(diff, end="")
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
