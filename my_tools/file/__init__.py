
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output

from my_tools.file.chdir import Cd
from my_tools.file.kill_process import KillProcess, KillParams
from my_tools.file.input import Input, InputParams
from my_tools.file.run import Run, RunParams
from my_tools.file.wait_process import WaitProcess, WaitParams


class MkdirParams(BaseModel):
    path: str = Field(
        description="The directory path to create.",
    )


class Mkdir(CallableTool2):
    name: str = "Mkdir"
    description: str = "Create a directory at the specified path. Supports recursive creation. If the directory already exists, it is considered successful."
    params: type[MkdirParams] = MkdirParams

    async def __call__(self, params: MkdirParams) -> ToolReturnValue:
        import os

        try:
            os.makedirs(params.path, exist_ok=True)
            return ToolOk(output=_maybe_export_output(f"Directory created: {params.path}"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create directory",
            )


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
            return ToolOk(output=_maybe_export_output("\n".join(lines) if lines else "(empty directory)"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to list files",
            )


class MvParams(BaseModel):
    src: str = Field(
        description="The source file or directory path to move.",
    )
    dest: str = Field(
        description="The destination path to move to.",
    )


class Mv(CallableTool2):
    name: str = "Mv"
    description: str = "Move a file or directory from src to dest. Supports moving directories recursively."
    params: type[MvParams] = MvParams

    async def __call__(self, params: MvParams) -> ToolReturnValue:
        import shutil

        try:
            shutil.move(params.src, params.dest)
            return ToolOk(output=_maybe_export_output(f"Moved '{params.src}' to '{params.dest}'"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to move file or directory",
            )


class CpParams(BaseModel):
    src: str = Field(
        description="The source file or directory path to copy.",
    )
    dest: str = Field(
        description="The destination path to copy to.",
    )


class Cp(CallableTool2):
    name: str = "Cp"
    description: str = "Copy a file or directory from src to dest. Supports copying directories recursively."
    params: type[CpParams] = CpParams

    async def __call__(self, params: CpParams) -> ToolReturnValue:
        import shutil
        import os

        try:
            if os.path.isdir(params.src):
                shutil.copytree(params.src, params.dest, dirs_exist_ok=True)
            else:
                shutil.copy2(params.src, params.dest)
            return ToolOk(output=_maybe_export_output(f"Copied '{params.src}' to '{params.dest}'"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to copy file or directory",
            )


class RmParams(BaseModel):
    path: str = Field(
        description="The file or directory path to delete.",
    )


class Rm(CallableTool2):
    name: str = "Rm"
    description: str = "Delete a file or directory at the specified path. Supports recursive deletion of directories."
    params: type[RmParams] = RmParams

    async def __call__(self, params: RmParams) -> ToolReturnValue:
        import shutil
        import os

        try:
            if os.path.isdir(params.path):
                shutil.rmtree(params.path)
            else:
                os.remove(params.path)
            return ToolOk(output=_maybe_export_output(f"Deleted: {params.path}"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to delete file or directory",
            )


class FileInfoParams(BaseModel):
    path: str = Field(
        description="The file or directory path to get information about.",
    )


class FileInfo(CallableTool2):
    name: str = "FileInfo"
    description: str = "Get detailed information about a file or directory, including size, permissions, timestamps, and hash."
    params: type[FileInfoParams] = FileInfoParams

    async def __call__(self, params: FileInfoParams) -> ToolReturnValue:
        import os
        import hashlib
        from datetime import datetime

        def compute_hash(file_path: str, algorithm: str = "sha256") -> str:
            """Compute the hash of a file."""
            hash_obj = hashlib.new(algorithm)
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()

        def format_size(size: int) -> str:
            """Format size in human-readable format."""
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size < 1024:
                    return f"{size:.2f} {unit}"
                size /= 1024
            return f"{size:.2f} PB"

        try:
            if not os.path.exists(params.path):
                return ToolError(
                    output="",
                    message=f"Path does not exist: {params.path}",
                    brief="Path not found",
                )

            stat = os.stat(params.path)
            is_dir = os.path.isdir(params.path)
            is_file = os.path.isfile(params.path)
            is_link = os.path.islink(params.path)

            info_lines = [
                f"Path: {params.path}",
                f"Type: {'Directory' if is_dir else 'Symbolic Link' if is_link else 'File'}",
                f"Size: {format_size(stat.st_size)} ({stat.st_size} bytes)",
                f"Permissions: {oct(stat.st_mode)[-3:]}",
                f"Owner UID: {stat.st_uid}",
                f"Group GID: {stat.st_gid}",
                f"Last Access Time: {datetime.fromtimestamp(stat.st_atime).strftime('%Y-%m-%d %H:%M:%S')}",
                f"Last Modify Time: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}",
                f"Creation Time: {datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}",
                f"Inode: {stat.st_ino}",
                f"Device: {stat.st_dev}",
                f"Hard Links: {stat.st_nlink}",
            ]

            if is_file and not is_link:
                try:
                    file_hash = compute_hash(params.path)
                    info_lines.append(f"SHA256: {file_hash}")
                except Exception:
                    info_lines.append("SHA256: (unable to compute)")

            if is_dir:
                try:
                    item_count = len(os.listdir(params.path))
                    info_lines.append(f"Items in directory: {item_count}")
                except Exception:
                    info_lines.append("Items in directory: (unable to count)")

            if is_link:
                try:
                    target = os.readlink(params.path)
                    info_lines.append(f"Link Target: {target}")
                except Exception:
                    info_lines.append("Link Target: (unable to read)")

            return ToolOk(output=_maybe_export_output("\n".join(info_lines)))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to get file information",
            )
