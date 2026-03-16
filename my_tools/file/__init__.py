from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    path: str = Field(
        description="The file path to get information from.",
    )


class FileInfo(CallableTool2):
    name: str = "FileInfo"
    description: str = "Get file information (last write time, SHA256, size, etc.)."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import os
        import hashlib
        from datetime import datetime

        try:
            if not os.path.exists(params.path):
                return ToolError(
                    output="",
                    message=f"Path does not exist: {params.path}",
                    brief="Path not found",
                )

            if os.path.isdir(params.path):
                return ToolError(
                    output="",
                    message=f"Path is a directory, not a file: {params.path}",
                    brief="Path is a directory",
                )

            stat = os.stat(params.path)

            # Calculate SHA256 hash
            sha256_hash = hashlib.sha256()
            with open(params.path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)

            # Format timestamps
            created_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
            modified_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
            accessed_time = datetime.fromtimestamp(stat.st_atime).isoformat()

            # Build result
            result = [
                f"Path: {params.path}",
                f"Size: {stat.st_size} bytes",
                f"SHA256: {sha256_hash.hexdigest()}",
                f"Created: {created_time}",
                f"Modified: {modified_time}",
                f"Accessed: {accessed_time}",
                f"Mode: {oct(stat.st_mode)}",
            ]

            return ToolOk(output="\n".join(result))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to get file information",
            )

class LsParams(BaseModel):
    directory: str = Field(
        default=".",
        description="The directory to list files from.",
    )
    # TODO add common shell params


class Ls(CallableTool2):
    name: str = "Ls"
    description: str = "List files in a directory."
    params: type[LsParams] = LsParams

    async def __call__(self, params: LsParams) -> ToolReturnValue:
        # TODO process shell param
        import os
        
        try:
            files = os.listdir(params.directory)
            return ToolOk(output="\n".join(files))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to list files",
            )
            

class MoveParams(BaseModel):
    source: str = Field(
        description="The source file or directory to move.",
    )
    destination: str = Field(
        description="The destination path to move to.",
    )


class Move(CallableTool2):
    name: str = "Move"
    description: str = "Move a directory or file to another path."
    params: type[MoveParams] = MoveParams

    async def __call__(self, params: MoveParams) -> ToolReturnValue:
        import shutil
        
        try:
            shutil.move(params.source, params.destination)
            return ToolOk(output=f"Moved '{params.source}' to '{params.destination}'")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to move file or directory",
            )

class CopyParams(BaseModel):
    source: str = Field(
        description="The source file or directory to move.",
    )
    destination: str = Field(
        description="The destination path to move to.",
    )


class Copy(CallableTool2):
    name: str = "Copy"
    description: str = "Copy a directory or file to another path."
    params: type[CopyParams] = CopyParams

    async def __call__(self, params: CopyParams) -> ToolReturnValue:
        import shutil
        
        try:
            shutil.copy2(params.source, params.destination)
            return ToolOk(output=f"Copyd '{params.source}' to '{params.destination}'")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to move file or directory",
            )

class RmParams(BaseModel):
    path: str = Field(
        description="The file or directory path to remove.",
    )
    recursive: bool = Field(
        default=False,
        description="If True, remove directories recursively. Required for non-empty directories.",
    )


class Remove(CallableTool2):
    name: str = "Remove"
    description: str = "Remove a file or directory."
    params: type[RmParams] = RmParams

    async def __call__(self, params: RmParams) -> ToolReturnValue:
        import os
        import shutil
        
        try:
            if not os.path.exists(params.path):
                return ToolError(
                    output="",
                    message=f"Path does not exist: {params.path}",
                    brief="Path not found",
                )
            
            if os.path.isdir(params.path):
                if params.recursive:
                    shutil.rmtree(params.path)
                else:
                    os.rmdir(params.path)
            else:
                os.remove(params.path)
            
            return ToolOk(output=f"Removed: {params.path}")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to remove path",
            )



class MkdirParams(BaseModel):
    path: str = Field(
        description="The path of the directory to create.",
    )
    parents: bool = Field(
        default=False,
        description="If True, create parent directories as needed. If False, raise an error if parent directories do not exist.",
    )


class Mkdir(CallableTool2):
    name: str = "Mkdir"
    description: str = "Create a directory on the target path."
    params: type[MkdirParams] = MkdirParams

    async def __call__(self, params: MkdirParams) -> ToolReturnValue:
        import os
        
        try:
            if params.parents:
                os.makedirs(params.path, exist_ok=True)
            else:
                os.mkdir(params.path)
            return ToolOk(output=f"Directory created: {params.path}")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create directory",
            )
