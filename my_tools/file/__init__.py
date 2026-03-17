from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class LsParams(BaseModel):
    directory: str = Field(
        default=".",
        description="The directory to list files from.",
    )
    long_format: bool = Field(
        default=False,
        description="If True, display detailed file information including permissions, owner, size, and modification time.",
    )
    recursive: bool = Field(
        default=False,
        description="If True, list files recursively including subdirectories.",
    )


class Ls(CallableTool2):
    name: str = "Ls"
    description: str = "List files in a directory."
    params: type[LsParams] = LsParams

    async def __call__(self, params: LsParams) -> ToolReturnValue:
        import os
        from datetime import datetime

        def format_file_info(path: str, name: str) -> str:
            """Format file info for long format listing."""
            full_path = os.path.join(path, name)
            try:
                stat = os.stat(full_path)
                size = stat.st_size
                mtime = datetime.fromtimestamp(
                    stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                ftype = "d" if os.path.isdir(full_path) else "-"
                mode = oct(stat.st_mode)[-3:]
                return f"{ftype}{mode:>9} {size:>10} {mtime} {name}"
            except Exception:
                return f"?????????? ???????? ?????????? {name}"

        def list_directory(path: str, prefix: str = "") -> list[str]:
            """List directory contents, optionally recursively."""
            result = []
            try:
                items = os.listdir(path)
            except Exception as exc:
                raise exc
            # Sort items (directories first, then alphabetically)
            items.sort(key=lambda x: (not os.path.isdir(
                os.path.join(path, x)), x.lower()))

            for item in items:
                if params.long_format:
                    result.append(prefix + format_file_info(path, item))
                else:
                    result.append(prefix + item)

                # Recursively list subdirectories if requested
                if params.recursive and os.path.isdir(os.path.join(path, item)):
                    result.append("")
                    subdir = os.path.join(path, item)
                    result.append(f"{prefix}{item}:")
                    result.extend(list_directory(subdir, prefix + "  "))

            return result

        try:
            lines = list_directory(params.directory)
            return ToolOk(output="\n".join(lines) if lines else "(empty directory)")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to list files",
            )
