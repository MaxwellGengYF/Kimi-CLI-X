import os
from pathlib import Path
from typing import Literal, override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from collections.abc import Callable

from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.file import FileActions
from kimi_cli.tools.file.check_fmt import check_json, check_xml
from kimi_cli.utils.logging import logger
from kimi_cli.utils.path import is_within_workspace
from kimi_cli.tools.file.plan_mode import inspect_plan_edit_target


_BASE_DESCRIPTION = (
    "Write content to a specific line. "
    "Modes: `overwrite` (replace) or `append` (insert). "
    "Line <1 prepends to start; line > file length appends to end."
)


class Params(BaseModel):
    path: str = Field(
        description="File path. Absolute paths required outside the working directory."
    )
    content: str = Field(description="Content to write.")
    line: int = Field(
        description="Line number (1-based) where content should be written.",
        default=1,
    )
    mode: Literal["overwrite", "append"] = Field(
        description="Write mode: overwrite (replace the line) or append (insert at the line).",
        default="overwrite",
    )


class WriteLine(CallableTool2[Params]):
    name: str = "WriteLine"
    description: str = _BASE_DESCRIPTION
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._work_dir = runtime.builtin_args.KIMI_WORK_DIR
        self._additional_dirs = runtime.additional_dirs
        self._plan_mode_checker: Callable[[], bool] | None = None
        self._plan_file_path_getter: Callable[[], Path | None] | None = None

    async def _validate_path(self, path: KaosPath) -> ToolError | None:
        """Validate that the path is safe to write."""
        resolved_path = path.canonical()

        if (
            not is_within_workspace(
                resolved_path, self._work_dir, self._additional_dirs)
            and not path.is_absolute()
        ):
            return ToolError(
                message=(
                    f"`{path}` is not an absolute path. "
                    "You must provide an absolute path to write a file "
                    "outside the working directory."
                ),
                brief="Invalid path",
            )
        return None

    def bind_plan_mode(
        self, checker: Callable[[], bool], path_getter: Callable[[], Path | None]
    ) -> None:
        """Bind plan mode state checker and plan file path getter."""
        self._plan_mode_checker = checker
        self._plan_file_path_getter = path_getter

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        if not params.path:
            return ToolError(
                message="File path cannot be empty.",
                brief="Empty file path",
            )

        try:
            p = KaosPath(params.path).expanduser()

            if err := await self._validate_path(p):
                return err
            p = p.canonical()
            plan_target = inspect_plan_edit_target(
                p,
                plan_mode_checker=self._plan_mode_checker,
                plan_file_path_getter=self._plan_file_path_getter,
            )
            if isinstance(plan_target, ToolError):
                return plan_target

            is_plan_file_write = plan_target.is_plan_target
            if is_plan_file_write and plan_target.plan_path is not None:
                plan_target.plan_path.parent.mkdir(parents=True, exist_ok=True)

            if not await p.parent.exists():
                try:
                    await p.parent.mkdir(parents=True)
                except:
                    return ToolError(
                        message=f"`{params.path}` parent directory does not exist.",
                        brief="Parent directory not found",
                    )

            # Validate mode parameter
            if params.mode not in ["overwrite", "append"]:
                return ToolError(
                    message=(
                        f"Invalid write mode: `{params.mode}`. "
                        "Mode must be either `overwrite` or `append`."
                    ),
                    brief="Invalid write mode",
                )

            # Read existing content or start with empty list
            lines: list[str] = []
            file_existed = await p.exists()
            if file_existed:
                text = await p.read_text(errors="replace")
                if text:
                    # Preserve line endings by not stripping newlines
                    lines = text.splitlines(keepends=True)
                    # If file doesn't end with newline, last line has no newline
                    # We handle this consistently

            # Determine effective line and mode
            line_count = len(lines)
            target_line = params.line
            effective_mode = params.mode

            # Adjust for negative or out-of-bounds line numbers
            if target_line < 1:
                target_line = 0  # Special value to indicate prepend to start
                effective_mode = "append"  # Prepend to file
            elif target_line > line_count:
                if line_count == 0:
                    target_line = 1
                else:
                    target_line = line_count + 1
                effective_mode = "append"  # Append to file

            # Convert to 0-based index (unless prepending)
            idx = target_line - 1 if target_line > 0 else 0

            # Prepare content with newline if it doesn't have one
            content = params.content
            if content and not content.endswith('\n'):
                content += '\n'

            # Perform the write operation
            if effective_mode == "append":
                if target_line == 0:
                    # Prepend to start of file
                    lines.insert(0, content)
                else:
                    # Insert at the specified position
                    lines.insert(idx, content)
            else:  # overwrite
                if line_count == 0:
                    # Empty file, just append the content
                    lines.append(content)
                elif idx < line_count:
                    # Replace the existing line
                    lines[idx] = content
                else:
                    # Should not happen due to bounds check above, but just in case
                    lines.append(content)

            # Write back to file
            new_text = "".join(lines)
            await p.write_text(new_text)

            # Get file info for success message
            file_size = (await p.stat()).st_size

            # Check file format for JSON/XML files
            fmt_error = None
            file_path_str = str(p)
            if file_path_str.lower().endswith(".json"):
                fmt_error = check_json(file_path_str)
            elif file_path_str.lower().endswith(".xml"):
                fmt_error = check_xml(file_path_str)
            if fmt_error:
                return ToolError(
                    message=f"Line written successfully, but format validation failed: {fmt_error}",
                    brief="Format validation failed",
                )

            if effective_mode == "overwrite":
                action_desc = "overwritten"
            elif target_line == 0:
                action_desc = "prepended"
            else:
                action_desc = "appended"
            line_desc = target_line if target_line > 0 else 1
            return ToolOk(
                output="",
                message=(
                    f"Line {line_desc} successfully {action_desc}. Current size: {file_size} bytes."),
                brief=f"Line {action_desc}",
            )

        except Exception as e:
            logger.warning(
                "WriteLine failed: {path}: {error}", path=params.path, error=e)
            return ToolError(
                message=f"Failed to write to {params.path}. Error: {e}",
                brief="Failed to write line",
            )
