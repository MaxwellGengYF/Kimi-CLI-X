"""Shared utilities for process management tools."""
from my_tools.common import _maybe_export_output
from my_tools.file._state import stdout_lines, output_queue
import queue


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
            data = output_queue.get_nowait()
            stdout_lines.append(data)
    except queue.Empty:
        pass
    s = "".join(stdout_lines)
    stdout_lines.clear()
    return s


def get_final_output(output_text=None):
    if output_text is None:
        output_text = get_output_text()
    return _maybe_export_output(output_text)


def _read_streams_into_queue(process: subprocess.Popen, streams, q: queue.Queue):
    """Read from multiple streams and put data into a single queue until stop_event is set.

    Args:
        streams: List of (stream, label) tuples where label is 'stdout' or 'stderr'
        q: Thread-safe queue for collecting output
        stop_event: Event to signal the thread to stop
    """
    import sys
    import time

    try:
        while process.poll() is None:
            any_data = False

            for stream, label in streams:
                if stream.closed:
                    continue

                try:
                    data = stream.read(1)
                    if data:
                        q.put(data)
                        any_data = True
                except (IOError, OSError, ValueError):
                    # Stream might be closed
                    continue
                except BlockingIOError:
                    # No data available (non-blocking mode)
                    continue

            # If no data was read, sleep briefly
            if not any_data:
                time.sleep(0.01)

    except Exception as e:
        import agent_utils
        agent_utils.print_error(str(e))
