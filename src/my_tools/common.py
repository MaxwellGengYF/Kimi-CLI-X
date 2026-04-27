import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from my_tools.background.utils import BackgroundStream
OUTPUT_TOKEN_LIMIT = 1024
_temp_folder = Path.home() / '.kimi' / 'sessions'
_temp_idx = 0
_temp_set: dict[Path, int] = dict()


def _estimate_tokens(text: str) -> int:
    """Rough estimation of token count (approximately 4 characters per token)."""
    return len(text) // 4


def _create_temp_file_name(ext: str = '.md') -> str:
    global _temp_idx
    id = _temp_idx
    _temp_idx += 1
    return str(_temp_folder / (str(id) + ext))


def _export_to_temp_file(key: Path | None, content: str, ext: str = '.txt') -> tuple[str, bool]:
    global _temp_idx
    """Export content to a temporary file and return the file path."""
    id = _temp_idx
    new_id = True
    if key:
        v = _temp_set.get(key)
        if v is not None:
            id = v
            new_id = False
        else:
            # Add key to _temp_set with the new id
            _temp_set[key] = id
    if new_id:
        _temp_idx += 1
    name = str(_temp_folder / (str(id) + ext))
    # Append content if key exists, otherwise overwrite/create
    mode = 'a' if not new_id else 'w'
    with open(name, mode, encoding='utf-8') as f:
        f.write(content)
    return name, new_id


async def _export_to_temp_file_async(key: Path | None, content: str, ext: str = '.txt') -> tuple[str, bool]:
    global _temp_idx
    """Async version: Export content to a temporary file and return the file path."""
    import anyio
    id = _temp_idx
    new_id = True
    if key:
        v = _temp_set.get(key)
        if v is not None:
            id = v
            new_id = False
        else:
            # Add key to _temp_set with the new id
            _temp_set[key] = id
    if new_id:
        _temp_idx += 1
    name = _temp_folder / (str(id) + ext)
    # Append content if key exists, otherwise overwrite/create
    mode = 'a' if not new_id else 'w'
    async with await anyio.open_file(name, mode, encoding='utf-8') as f:
        await f.write(content)
    return str(name), new_id


def _maybe_export_output(output: str, key: Path | None = None) -> str:
    """Check if output is too large and export to temp file if needed.

    Args:
        output: The output string to check.
        key: Optional Path to normalize and use in the output message.

    Returns:
        The output string, or a message indicating it was exported to a temp file.
    """
    if not output:
        return ''
    if _estimate_tokens(output) > OUTPUT_TOKEN_LIMIT:
        if key is not None:
            if type(key) is not Path:
                key = Path(key)
            key = key.resolve()
        temp_path, new_id = _export_to_temp_file(key, output)
        return f"Output too large, {'exported' if new_id else 'added'} to file `{temp_path}`"
    return output


async def _maybe_export_output_async(output: str, key: Path | None = None) -> str:
    """Async version: Check if output is too large and export to temp file if needed.

    Args:
        output: The output string to check.
        key: Optional Path to normalize and use in the output message.

    Returns:
        The output string, or a message indicating it was exported to a temp file.
    """
    if not output:
        return ''
    if _estimate_tokens(output) > OUTPUT_TOKEN_LIMIT:
        if key is not None:
            if type(key) is not Path:
                key = Path(key)
            key = key.resolve()
        temp_path, new_id = await _export_to_temp_file_async(key, output)
        return f"[Output too large, {'exported' if new_id else 'added'} to file: {temp_path}]"
    return output


class ProcessTask:
    """Run a subprocess in the background with stream output and input support."""

    def __init__(self, path: str, args: list[str] | None = None, cwd: str | None = None, timeout: float | None = None) -> None:
        import shutil
        # On Windows, subprocess.Popen with shell=False does not resolve .cmd/.bat
        # via PATHEXT. Use shutil.which to find the real executable (e.g. pnpm.CMD).
        if not Path(path).exists():
            resolved = shutil.which(path)
            if resolved:
                path = resolved
        self.path = path
        self.args = args or []
        self.cwd = cwd
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._process_ref: subprocess.Popen[str] | None = None
        self._stream: 'BackgroundStream' | None = None
        self._task_id: str | None = None

    def _run_process_bg(self, q: queue.Queue[str]) -> bool:
        """Run the process and collect output into the queue."""
        process = None
        try:
            if self._stop_event.is_set():
                return False
            # Start the process
            process = subprocess.Popen(
                [self.path] + self.args,
                cwd=self.cwd,
                env=os.environ,
                stdin=subprocess.PIPE,  # Allow input via input_function
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            self._process_ref = process
            # Read stdout and stderr concurrently with stop checking

            assert process.stdout is not None
            assert process.stderr is not None

            def read_stream(stream: IO[str], is_stderr: bool = False) -> None:
                try:
                    while True:
                        if stream.closed or self._stop_event.is_set():
                            break
                        data = stream.read()
                        if data:
                            prefix = "[stderr] " if is_stderr else ""
                            q.put_nowait(prefix + data)
                        else:
                            time.sleep(0.01)
                except (IOError, OSError, ValueError):
                    pass

            def read_stream_one(stream: IO[str]) -> None:
                try:
                    while True:
                        if stream.closed or self._stop_event.is_set():
                            break
                        data = stream.read(1)
                        if data:
                            q.put_nowait(data)
                        else:
                            time.sleep(0.01)
                except (IOError, OSError, ValueError):
                    pass

            # Start reader threads
            stdout_thread = threading.Thread(
                target=read_stream_one, args=(
                    process.stdout, ), daemon=True
            )
            stderr_thread = threading.Thread(
                target=read_stream, args=(process.stderr, True), daemon=True
            )
            stdout_thread.start()
            stderr_thread.start()
            # Wait for process completion with periodic stop checking
            start_time = time.time()
            is_timeout = False
            while process.poll() is None:
                if self._stop_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
                if self.timeout is not None and time.time() - start_time > self.timeout:
                    q.put_nowait(
                        f"\n[Process timed out after {self.timeout} seconds]")
                    self._stop_event.set()
                    is_timeout = True
                time.sleep(0.1)

            # Signal EOF to readers so they exit promptly
            try:
                if process.stdout is not None:
                    process.stdout.close()
            except Exception:
                pass
            try:
                if process.stderr is not None:
                    process.stderr.close()
            except Exception:
                pass

            # Wait for readers to finish
            stdout_thread.join(timeout=60)
            stderr_thread.join(timeout=60)
            # Read any remaining data from stdout and stderr
            try:
                if process.stdout is not None:
                    remaining_stdout = process.stdout.read()
                    if remaining_stdout:
                        q.put_nowait(remaining_stdout)
            except (IOError, OSError, ValueError):
                pass
            try:
                if process.stderr is not None:
                    remaining_stderr = process.stderr.read()
                    if remaining_stderr:
                        q.put_nowait("[stderr] " + remaining_stderr)
            except (IOError, OSError, ValueError):
                pass
            # Report completion status
            return_code = process.poll()
            if self._stop_event.is_set():
                if not is_timeout:
                    q.put_nowait("\n[Process stopped by user]")
                return False
            elif return_code is not None and return_code != 0:
                q.put_nowait(f"\n[Process exited with code {return_code}]")
                return False
            return True

        except Exception as e:
            q.put_nowait(f"\n[Error: {str(e)}]")
            return False
        finally:
            self._stop_event.set()
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except:
                    pass

    def _stop_function(self) -> None:
        """Signal the background process to stop."""
        self._stop_event.set()
        # Also try to terminate the process directly if it's running
        proc = self._process_ref
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _input_function(self, data: str) -> bool:
        """Push data to the process's stdin.

        Args:
            data: The string data to write to stdin.

        Returns:
            True if data was written successfully, False otherwise.
        """
        proc = None
        # Wait for the process to be available
        while True:
            if self._stop_event.is_set():
                return False
            proc = self._process_ref
            if proc is None:
                time.sleep(0.05)
            else:
                break

        # Write data to stdin
        try:
            if proc.stdin is not None and proc.poll() is None:
                proc.stdin.write(data)
                proc.stdin.flush()
                return True
        except (IOError, OSError, ValueError):
            # Process may have terminated or stdin is closed
            pass
        return False

    def start(self, session_id: str, kind: str = "run", name: str | None = None) -> str:
        """Start the background process and register it as a task.

        Args:
            session_id: The session identifier.
            kind: Task kind prefix for the task ID.
            name: Optional name for the task ID (defaults to the executable stem).

        Returns:
            The generated task ID.
        """
        from my_tools.background.utils import BackgroundStream, generate_task_id, add_task
        self._stream = BackgroundStream()
        # Generate a task ID based on the executable name
        self._task_id = generate_task_id(session_id, kind, name or Path(self.path).stem)
        self._stream.start(self._run_process_bg,
                           self._stop_function, self._input_function)
        # Register the task
        add_task(session_id, self._task_id, self._stream)
        assert self._task_id is not None
        return self._task_id

    def wait(self, timeout: float | None = None) -> None:
        self._stream.wait(timeout)

    def thread_is_alive(self) -> bool:
        return self._stream.thread_is_alive()

    def stop(self) -> None:
        """Stop the background process."""
        if self._stream is not None:
            self._stream.stop()

    def input(self, data: str) -> bool:
        """Push data to the process's stdin.

        Args:
            data: The string data to write to stdin.

        Returns:
            True if data was written successfully, False otherwise.
        """
        if self._stream is not None:
            return bool(self._stream.input(data))
        return False

    @property
    def task_id(self) -> str | None:
        """The task ID if the process has been started."""
        return self._task_id

    @property
    def stream(self) -> 'BackgroundStream' | None:
        """The underlying BackgroundStream if the process has been started."""
        return self._stream

