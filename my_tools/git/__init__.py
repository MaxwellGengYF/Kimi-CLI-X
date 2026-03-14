"""Git tool for regular git operations."""

import os
import subprocess
from typing import Optional, List
from pydantic import BaseModel, Field
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue


def _run_git_command(args: List[str], cwd: Optional[str] = None) -> tuple[str, int]:
    """Run a git command and return (output, return_code)."""
    command = ["git"] + args
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.strip(), result.returncode
    except Exception as exc:
        return str(exc), 1


class StatusParams(BaseModel):
    path: str = Field(default=".", description="The path to the git repository.")


class GitStatus(CallableTool2):
    """Check the status of a git repository."""
    name: str = "GitStatus"
    description: str = "Show the working tree status of a git repository."
    params: type[StatusParams] = StatusParams

    async def __call__(self, params: StatusParams) -> ToolReturnValue:
        output, code = _run_git_command(["status"], cwd=params.path)
        if code == 0:
            return ToolOk(output=output)
        return ToolError(output=output, message=f"Git status failed with code {code}", brief="Failed to get git status")


class AddParams(BaseModel):
    path: str = Field(default=".", description="The path to the file or directory to add. Use '.' to add all changes.")
    repo_path: str = Field(default=".", description="The path to the git repository.")


class GitAdd(CallableTool2):
    """Add file contents to the index (staging area)."""
    name: str = "GitAdd"
    description: str = "Add file contents to the index. Use path='.' to stage all changes."
    params: type[AddParams] = AddParams

    async def __call__(self, params: AddParams) -> ToolReturnValue:
        output, code = _run_git_command(["add", params.path], cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=f"Successfully added {params.path}" if output == "" else output)
        return ToolError(output=output, message=f"Git add failed with code {code}", brief="Failed to add files")


class CommitParams(BaseModel):
    message: str = Field(description="The commit message.")
    repo_path: str = Field(default=".", description="The path to the git repository.")
    allow_empty: bool = Field(default=False, description="Allow creating an empty commit.")


class GitCommit(CallableTool2):
    """Record changes to the repository."""
    name: str = "GitCommit"
    description: str = "Create a new commit with the staged changes."
    params: type[CommitParams] = CommitParams

    async def __call__(self, params: CommitParams) -> ToolReturnValue:
        args = ["commit", "-m", params.message]
        if params.allow_empty:
            args.append("--allow-empty")
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output)
        return ToolError(output=output, message=f"Git commit failed with code {code}", brief="Failed to commit")


class PushParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    remote: str = Field(default="origin", description="The remote name.")
    branch: Optional[str] = Field(default=None, description="The branch name. If not specified, pushes the current branch.")
    force: bool = Field(default=False, description="Force push (use with caution).")


class GitPush(CallableTool2):
    """Update remote refs along with associated objects."""
    name: str = "GitPush"
    description: str = "Push commits to a remote repository."
    params: type[PushParams] = PushParams

    async def __call__(self, params: PushParams) -> ToolReturnValue:
        args = ["push", params.remote]
        if params.branch:
            args.append(params.branch)
        if params.force:
            args.append("--force")
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "Push successful")
        return ToolError(output=output, message=f"Git push failed with code {code}", brief="Failed to push")


class PullParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    remote: str = Field(default="origin", description="The remote name.")
    branch: Optional[str] = Field(default=None, description="The branch to pull from.")
    rebase: bool = Field(default=False, description="Rebase the current branch on top of the upstream branch.")


class GitPull(CallableTool2):
    """Fetch from and integrate with another repository or a local branch."""
    name: str = "GitPull"
    description: str = "Pull changes from a remote repository."
    params: type[PullParams] = PullParams

    async def __call__(self, params: PullParams) -> ToolReturnValue:
        args = ["pull", params.remote]
        if params.branch:
            args.append(params.branch)
        if params.rebase:
            args.append("--rebase")
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "Pull successful")
        return ToolError(output=output, message=f"Git pull failed with code {code}", brief="Failed to pull")


class CloneParams(BaseModel):
    url: str = Field(description="The URL of the repository to clone.")
    destination: Optional[str] = Field(default=None, description="The directory to clone into. If not specified, uses the repository name.")
    branch: Optional[str] = Field(default=None, description="The branch to clone.")
    depth: Optional[int] = Field(default=None, description="Create a shallow clone with a history truncated to the specified number of commits.")


class GitClone(CallableTool2):
    """Clone a repository into a new directory."""
    name: str = "GitClone"
    description: str = "Clone a remote git repository to the local machine."
    params: type[CloneParams] = CloneParams

    async def __call__(self, params: CloneParams) -> ToolReturnValue:
        args = ["clone"]
        if params.depth:
            args.extend(["--depth", str(params.depth)])
        if params.branch:
            args.extend(["--branch", params.branch])
        args.append(params.url)
        if params.destination:
            args.append(params.destination)
        output, code = _run_git_command(args)
        if code == 0:
            return ToolOk(output=output if output else f"Successfully cloned {params.url}")
        return ToolError(output=output, message=f"Git clone failed with code {code}", brief="Failed to clone repository")


class LogParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    max_count: int = Field(default=10, description="Limit the number of commits to output.")
    oneline: bool = Field(default=True, description="Show each commit in a single line.")
    branch: Optional[str] = Field(default=None, description="The branch to show log for.")


class GitLog(CallableTool2):
    """Show commit logs."""
    name: str = "GitLog"
    description: str = "Display the commit history of the repository."
    params: type[LogParams] = LogParams

    async def __call__(self, params: LogParams) -> ToolReturnValue:
        args = ["log"]
        if params.oneline:
            args.append("--oneline")
        args.extend(["-n", str(params.max_count)])
        if params.branch:
            args.append(params.branch)
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output)
        return ToolError(output=output, message=f"Git log failed with code {code}", brief="Failed to get log")


class DiffParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    target: Optional[str] = Field(default=None, description="The commit, branch, or file to compare against. Use 'HEAD' for staged changes vs last commit.")
    staged: bool = Field(default=False, description="Show staged changes (diff of the index).")
    path: Optional[str] = Field(default=None, description="Specific file path to diff.")


class GitDiff(CallableTool2):
    """Show changes between commits, commit and working tree, etc."""
    name: str = "GitDiff"
    description: str = "Show differences between commits, branches, or working directory."
    params: type[DiffParams] = DiffParams

    async def __call__(self, params: DiffParams) -> ToolReturnValue:
        args = ["diff"]
        if params.staged:
            args.append("--staged")
        if params.target:
            args.append(params.target)
        if params.path:
            args.append(params.path)
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "No differences found")
        return ToolError(output=output, message=f"Git diff failed with code {code}", brief="Failed to get diff")


class BranchParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    list_all: bool = Field(default=False, description="List both remote-tracking and local branches.")
    create: Optional[str] = Field(default=None, description="Create a new branch with the given name.")
    delete: Optional[str] = Field(default=None, description="Delete the specified branch.")
    force_delete: bool = Field(default=False, description="Force delete the branch (even if not merged).")


class GitBranch(CallableTool2):
    """List, create, or delete branches."""
    name: str = "GitBranch"
    description: str = "Manage git branches - list, create, or delete them."
    params: type[BranchParams] = BranchParams

    async def __call__(self, params: BranchParams) -> ToolReturnValue:
        if params.create:
            args = ["branch", params.create]
        elif params.delete:
            args = ["branch", "-D" if params.force_delete else "-d", params.delete]
        else:
            args = ["branch"]
            if params.list_all:
                args.append("-a")
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "Branch operation successful")
        return ToolError(output=output, message=f"Git branch failed with code {code}", brief="Failed to manage branch")


class CheckoutParams(BaseModel):
    target: str = Field(description="The branch, tag, or commit to checkout.")
    repo_path: str = Field(default=".", description="The path to the git repository.")
    create_new: bool = Field(default=False, description="Create a new branch and switch to it (-b flag).")


class GitCheckout(CallableTool2):
    """Switch branches or restore working tree files."""
    name: str = "GitCheckout"
    description: str = "Switch to a different branch or checkout files."
    params: type[CheckoutParams] = CheckoutParams

    async def __call__(self, params: CheckoutParams) -> ToolReturnValue:
        args = ["checkout"]
        if params.create_new:
            args.append("-b")
        args.append(params.target)
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else f"Switched to {params.target}")
        return ToolError(output=output, message=f"Git checkout failed with code {code}", brief="Failed to checkout")


class MergeParams(BaseModel):
    branch: str = Field(description="The branch to merge into the current branch.")
    repo_path: str = Field(default=".", description="The path to the git repository.")
    no_ff: bool = Field(default=False, description="Create a merge commit even when the merge resolves as a fast-forward.")
    message: Optional[str] = Field(default=None, description="The commit message for the merge commit.")


class GitMerge(CallableTool2):
    """Join two or more development histories together."""
    name: str = "GitMerge"
    description: str = "Merge a branch into the current branch."
    params: type[MergeParams] = MergeParams

    async def __call__(self, params: MergeParams) -> ToolReturnValue:
        args = ["merge"]
        if params.no_ff:
            args.append("--no-ff")
        if params.message:
            args.extend(["-m", params.message])
        args.append(params.branch)
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else f"Successfully merged {params.branch}")
        return ToolError(output=output, message=f"Git merge failed with code {code}", brief="Failed to merge")


class ResetParams(BaseModel):
    target: Optional[str] = Field(default=None, description="The commit or reference to reset to.")
    repo_path: str = Field(default=".", description="The path to the git repository.")
    hard: bool = Field(default=False, description="Reset the index and working tree (discard all local changes).")
    soft: bool = Field(default=False, description="Reset only the HEAD, keep changes staged.")
    mixed: bool = Field(default=False, description="Reset the index but not the working tree (default).")


class GitReset(CallableTool2):
    """Reset current HEAD to the specified state."""
    name: str = "GitReset"
    description: str = "Reset the current HEAD to a specified state. Use with caution."
    params: type[ResetParams] = ResetParams

    async def __call__(self, params: ResetParams) -> ToolReturnValue:
        args = ["reset"]
        if params.hard:
            args.append("--hard")
        elif params.soft:
            args.append("--soft")
        elif params.mixed:
            args.append("--mixed")
        if params.target:
            args.append(params.target)
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "Reset successful")
        return ToolError(output=output, message=f"Git reset failed with code {code}", brief="Failed to reset")


class RemoteParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    action: str = Field(default="list", description="Action to perform: 'list', 'add', 'remove', 'set-url'.")
    name: Optional[str] = Field(default=None, description="Name of the remote (for add/remove/set-url).")
    url: Optional[str] = Field(default=None, description="URL of the remote (for add/set-url).")


class GitRemote(CallableTool2):
    """Manage set of tracked repositories."""
    name: str = "GitRemote"
    description: str = "Manage remote repositories - list, add, remove, or update URLs."
    params: type[RemoteParams] = RemoteParams

    async def __call__(self, params: RemoteParams) -> ToolReturnValue:
        if params.action == "add":
            if not params.name or not params.url:
                return ToolError(output="", message="Both 'name' and 'url' are required for 'add'", brief="Missing parameters")
            args = ["remote", "add", params.name, params.url]
        elif params.action == "remove":
            if not params.name:
                return ToolError(output="", message="'name' is required for 'remove'", brief="Missing parameter")
            args = ["remote", "remove", params.name]
        elif params.action == "set-url":
            if not params.name or not params.url:
                return ToolError(output="", message="Both 'name' and 'url' are required for 'set-url'", brief="Missing parameters")
            args = ["remote", "set-url", params.name, params.url]
        else:  # list
            args = ["remote", "-v"]
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "Remote operation successful")
        return ToolError(output=output, message=f"Git remote failed with code {code}", brief="Failed to manage remote")


class FetchParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    remote: str = Field(default="origin", description="The remote to fetch from.")
    all_remotes: bool = Field(default=False, description="Fetch from all remotes.")
    prune: bool = Field(default=False, description="Remove remote-tracking references that no longer exist on the remote.")


class GitFetch(CallableTool2):
    """Download objects and refs from another repository."""
    name: str = "GitFetch"
    description: str = "Fetch updates from a remote repository without merging."
    params: type[FetchParams] = FetchParams

    async def __call__(self, params: FetchParams) -> ToolReturnValue:
        if params.all_remotes:
            args = ["fetch", "--all"]
        else:
            args = ["fetch", params.remote]
        if params.prune:
            args.append("--prune")
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else "Fetch successful")
        return ToolError(output=output, message=f"Git fetch failed with code {code}", brief="Failed to fetch")


class StashParams(BaseModel):
    repo_path: str = Field(default=".", description="The path to the git repository.")
    action: str = Field(default="save", description="Action: 'save', 'pop', 'apply', 'list', 'drop', 'clear'.")
    message: Optional[str] = Field(default=None, description="Message for the stash (for 'save').")
    stash_ref: Optional[str] = Field(default=None, description="Stash reference (for 'pop', 'apply', 'drop').")


class GitStash(CallableTool2):
    """Stash changes in a dirty working directory."""
    name: str = "GitStash"
    description: str = "Stash and unstash changes - save, restore, or manage stashes."
    params: type[StashParams] = StashParams

    async def __call__(self, params: StashParams) -> ToolReturnValue:
        args = ["stash", params.action]
        if params.action == "save" and params.message:
            args.extend(["-m", params.message])
        elif params.action in ["pop", "apply", "drop"] and params.stash_ref:
            args.append(params.stash_ref)
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output if output else f"Stash {params.action} successful")
        return ToolError(output=output, message=f"Git stash failed with code {code}", brief="Failed to stash")


class ShowParams(BaseModel):
    target: str = Field(default="HEAD", description="The commit, branch, or tag to show information for.")
    repo_path: str = Field(default=".", description="The path to the git repository.")
    stat: bool = Field(default=False, description="Show diffstat instead of full diff.")
    name_only: bool = Field(default=False, description="Show only names of changed files.")


class GitShow(CallableTool2):
    """Show various types of objects (commits, tags, etc.)."""
    name: str = "GitShow"
    description: str = "Show information about a git object (commit, tag, etc.)."
    params: type[ShowParams] = ShowParams

    async def __call__(self, params: ShowParams) -> ToolReturnValue:
        args = ["show", params.target]
        if params.stat:
            args.append("--stat")
        if params.name_only:
            args.append("--name-only")
        output, code = _run_git_command(args, cwd=params.repo_path)
        if code == 0:
            return ToolOk(output=output)
        return ToolError(output=output, message=f"Git show failed with code {code}", brief="Failed to show")


# Export all tools
__all__ = [
    "GitStatus",
    "GitAdd",
    "GitCommit",
    "GitPush",
    "GitPull",
    "GitClone",
    "GitLog",
    "GitDiff",
    "GitBranch",
    "GitCheckout",
    "GitMerge",
    "GitReset",
    "GitRemote",
    "GitFetch",
    "GitStash",
    "GitShow",
]
