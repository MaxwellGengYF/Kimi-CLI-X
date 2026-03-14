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
