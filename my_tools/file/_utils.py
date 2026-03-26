"""Shared utilities for process management tools."""
from my_tools.common import _maybe_export_output
import subprocess
import threading
import queue
from typing import Optional
import io


class ProcessState:
    """Global state for process management."""

    def __init__(self):
        import time
        self.last_write_time = time.time()
        self.stdout_lines = io.StringIO()
        self.output_queue: queue.Queue = queue.Queue()
        self.reader_threads = None
        self.process: Optional[subprocess.Popen] = None
        self.name = None
        self.detect_input = None

    def set_process(self, p: Optional[subprocess.Popen], detect_input = None):
        """Set the process."""
        if p is None:
            self.name = None
        self.process = p
        self.detect_input = detect_input

    def set_reader_threads(self, t: list | None):
        """Set the reader thread."""
        self.reader_threads = t

    def join(self, timeout=None):
        if not self.reader_threads:
            return
        for i in self.reader_threads:
            i.join(timeout=timeout)
        self.reader_threads = []

    def start(self):
        if not self.reader_threads:
            return
        for i in self.reader_threads:
            i.start()

    def set_stdout_lines(self):
        """Set the stdout_lines."""
        self.stdout_lines.truncate(0)
        self.stdout_lines.seek(0)


# Global ProcessState instance
_state = ProcessState()


# Keywords that indicate the process is waiting for user input
INPUT_KEYWORDS = [
    "input", "choose", "enter",
    "prompt", "write", "provide",
    "confirm", "yes/no", "y/n"
]


def _check_for_input_prompt(text: str) -> bool:
    """Check if the text contains keywords indicating the process is waiting for input."""
    text_lower = text.lower()
    for keyword in INPUT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


def get_output_text():
    try:
        while True:
            data = _state.output_queue.get_nowait()
            _state.stdout_lines.write(data)
    except queue.Empty:
        pass
    return _state.stdout_lines.getvalue()


def get_final_output():
    output_text = get_output_text()
    _state.set_stdout_lines()
    return _maybe_export_output(output_text, _state.name)


def _read_streams_into_queue(process: subprocess.Popen, stream, q: queue.Queue, may_input: bool = False):
    """Read from multiple streams and put data into a single queue until stop_event is set.

    Args:
        streams: List of (stream, label) tuples where label is 'stdout' or 'stderr'
        q: Thread-safe queue for collecting output
        stop_event: Event to signal the thread to stop
    """
    import time

    try:
        while process.poll() is None:
            any_data = False
            if stream.closed:
                continue
            try:
                if may_input:
                    data = stream.read(1)
                else:
                    data = stream.read()
                if data:
                    any_data = True
                    q.put_nowait(data)
                    data = None
            except (IOError, OSError, ValueError):
                # Stream might be closed
                continue
            except BlockingIOError:
                # No data available (non-blocking mode)
                continue

            # Flush remaining data if no new data (ensures timely output)
            if not any_data:
                _state.last_write_time = time.time()
                time.sleep(0.01)

        # Final flush of any remaining data

    except Exception as e:
        import agent_utils
        agent_utils.print_error(str(e))


def get_state():
    return _state
