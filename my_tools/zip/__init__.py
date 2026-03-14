from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from pathlib import Path
import os

def _format_size(size: int) -> str:
    """Format size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

class Params(BaseModel):
    source: str = Field(
        description="The file or directory path to compress.",
    )
    destination: str = Field(
        description="The output 7z file path. If not specified, will use the source name with .7z extension.",
        default="",
    )
    password: str = Field(
        description="Optional password for encryption.",
        default="",
    )


class Zip(CallableTool2):
    name: str = "Zip"
    description: str = "Zip a file or directory as 7z archive."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import os
        import subprocess

        source = params.source
        
        # Validate source exists
        if not os.path.exists(source):
            return ToolError(
                output="",
                message=f"Source path does not exist: {source}",
                brief="Source not found",
            )

        # Determine destination path
        if params.destination:
            dest = params.destination
        else:
            # Default: use source name with .7z extension
            if os.path.isdir(source):
                dest = source.rstrip(os.sep) + ".7z"
            else:
                dest = source + ".7z"

        # Ensure destination has .7z extension
        if not dest.endswith(".7z"):
            dest += ".7z"

        # Check if 7z command is available
        seven_zip_cmd = None
        for cmd in [
            "7z",
            "7za",
            "7zr",
            # Windows common installation paths
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            # Linux/macOS common paths
            "/usr/bin/7z",
            "/usr/local/bin/7z",
            "/opt/local/bin/7z",
        ]:
            try:
                result = subprocess.run(
                    [cmd, "--help"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0 or result.returncode == 7:  # 7z returns 7 for --help
                    seven_zip_cmd = cmd
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        if not seven_zip_cmd:
            return ToolError(
                output="",
                message="7z command not found. Please install 7-Zip (p7zip).",
                brief="7z not found",
            )

        try:
            # Build the 7z command
            cmd_args = [seven_zip_cmd, "a", "-t7z", "-m0=lzma2", "-mx=5"]
            
            # Add password if specified
            if params.password:
                cmd_args.extend(["-p" + params.password, "-mhe=on"])
            else:
                cmd_args.append("-p-")  # No password
            
            cmd_args.append(dest)
            cmd_args.append(source)

            # Run the compression command
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )

            if result.returncode == 0:
                # Get archive size
                archive_size = os.path.getsize(dest) if os.path.exists(dest) else 0
                
                # Calculate source size
                if os.path.isfile(source):
                    source_size = os.path.getsize(source)
                else:
                    source_size = self._get_dir_size(source)

                output_lines = [
                    f"Successfully created 7z archive: {dest}",
                    f"Source: {source}",
                    f"Source size: {_format_size(source_size)}",
                    f"Archive size: {_format_size(archive_size)}",
                ]
                
                if source_size > 0:
                    ratio = (1 - archive_size / source_size) * 100
                    output_lines.append(f"Compression ratio: {ratio:.1f}%")

                return ToolOk(output="\n".join(output_lines))
            else:
                return ToolError(
                    output=result.stdout + "\n" + result.stderr,
                    message=f"7z command failed with exit code: {result.returncode}",
                    brief="Compression failed",
                )

        except subprocess.TimeoutExpired:
            return ToolError(
                output="",
                message="Compression timed out after 5 minutes.",
                brief="Compression timeout",
            )
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create archive",
            )

    def _get_dir_size(self, path: str) -> int:
        """Calculate total size of a directory."""
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
        return total


class UnzipParams(BaseModel):
    source: str = Field(
        description="The archive file path to extract.",
    )
    destination: str = Field(
        description="The output directory path. If not specified, will extract to the same directory as the archive.",
        default="",
    )
    password: str = Field(
        description="Optional password for encrypted archives.",
        default="",
    )


class Unzip(CallableTool2):
    name: str = "Unzip"
    description: str = "Extract a 7z/zip/rar/tar/gz archive."
    params: type[UnzipParams] = UnzipParams

    async def __call__(self, params: UnzipParams) -> ToolReturnValue:
        import os
        import subprocess

        source = params.source

        # Validate source exists
        if not os.path.exists(source):
            return ToolError(
                output="",
                message=f"Archive file does not exist: {source}",
                brief="Archive not found",
            )

        # Validate source is a file
        if not os.path.isfile(source):
            return ToolError(
                output="",
                message=f"Source path is not a file: {source}",
                brief="Not a file",
            )

        # Determine destination path
        if params.destination:
            dest = params.destination
        else:
            # Default: use the same directory as the archive
            dest = os.path.dirname(source) or "."

        # Ensure destination directory exists
        os.makedirs(dest, exist_ok=True)

        # Check if 7z command is available
        seven_zip_cmd = None
        for cmd in [
            "7z",
            "7za",
            "7zr",
            # Windows common installation paths
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            # Linux/macOS common paths
            "/usr/bin/7z",
            "/usr/local/bin/7z",
            "/opt/local/bin/7z",
        ]:
            try:
                result = subprocess.run(
                    [cmd, "--help"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0 or result.returncode == 7:  # 7z returns 7 for --help
                    seven_zip_cmd = cmd
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        if not seven_zip_cmd:
            return ToolError(
                output="",
                message="7z command not found. Please install 7-Zip (p7zip).",
                brief="7z not found",
            )

        try:
            # First, list the archive contents to get info
            list_args = [seven_zip_cmd, "l", source]
            if params.password:
                list_args.extend(["-p" + params.password])
            else:
                list_args.append("-p-")

            list_result = subprocess.run(
                list_args,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Build the extraction command
            cmd_args = [seven_zip_cmd, "x", "-y", "-o" + dest]

            # Add password if specified
            if params.password:
                cmd_args.extend(["-p" + params.password])
            else:
                cmd_args.append("-p-")  # No password

            cmd_args.append(source)

            # Run the extraction command
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )

            if result.returncode == 0:
                # Get archive size
                archive_size = os.path.getsize(source)

                # Calculate extracted size
                extracted_size = self._get_extracted_size(dest, source)

                output_lines = [
                    f"Successfully extracted archive: {source}",
                    f"Destination: {dest}",
                    f"Archive size: {_format_size(archive_size)}",
                    f"Extracted size: {_format_size(extracted_size)}",
                ]

                if archive_size > 0:
                    ratio = (extracted_size / archive_size - 1) * 100
                    output_lines.append(f"Size change: +{ratio:.1f}%")

                return ToolOk(output="\n".join(output_lines))
            else:
                return ToolError(
                    output=result.stdout + "\n" + result.stderr,
                    message=f"7z extraction failed with exit code: {result.returncode}",
                    brief="Extraction failed",
                )

        except subprocess.TimeoutExpired:
            return ToolError(
                output="",
                message="Extraction timed out after 5 minutes.",
                brief="Extraction timeout",
            )
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to extract archive",
            )

    def _get_extracted_size(self, dest: str, source: str) -> int:
        """Calculate total size of extracted files."""
        total = 0
        for dirpath, dirnames, filenames in os.walk(dest):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    # Skip the source archive if it's in the destination
                    if os.path.samefile(fp, source):
                        continue
                    total += os.path.getsize(fp)
        return total
