import threading
import queue
from typing import Callable

_ALL_TASK_NAMES: set[str] = set()


class BackgroundStream:
    """A wrapper for background thread execution with a thread-safe queue."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue[str] | None = None
        self._started: bool = False
        self._stopped: bool = False
        self._stop_function: Callable = None
        self._input_function: Callable = None
        self._lock = threading.Lock()

    def start(self, function: Callable[[queue.Queue[str]], None], stop_function: Callable, input_function: Callable | None = None) -> None:
        """Start the background thread with the given function.

        Args:
            function: A callable that accepts a queue.Queue[str] as its argument.
                     The function can put strings into the queue for retrieval by other threads.
        """
        with self._lock:
            if self._started:
                return

            self._queue = queue.Queue()
            self._thread = threading.Thread(
                target=function, args=(self._queue,), daemon=True)
            self._thread.start()
            self._stop_function = stop_function
            self._input_function = input_function
            self._started = True

    def input(self, data: str) -> bool:
        if self._input_function:
            self._input_function(data)
            return True
        return False

    def wait(self) -> None:
        """Wait for the background thread to complete."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._thread.join()
                self._thread = None

    def pop_output(self) -> str:
        """Pop all output from the queue and return as a single string.

        Returns:
            Concatenated string of all queue contents. Empty string if queue is None.
        """
        if self._queue is None:
            return ""

        lines = []
        while not self._queue.empty():
            try:
                lines.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return "".join(lines)

    def get_queue(self) -> queue.Queue[str] | None:
        """Get the thread-safe queue for retrieving messages.

        Returns:
            The queue if started, None otherwise.
        """
        return self._queue

    def is_started(self) -> bool:
        """Check if the stream has been started."""
        return self._started

    def is_stopped(self) -> bool:
        """Check if the stream has been stopped."""
        return self._stopped

    def stop(self) -> bool:
        """Stop the background thread.

        Returns:
            True if the thread was stopped, False if it was not running.
        """
        with self._lock:
            if not self._started or self._stopped:
                return False
            self._stopped = True
            if self._thread is not None and self._thread.is_alive():
                if self._stop_function is not None:
                    try:
                        self._stop_function()
                    except Exception:
                        pass
                return True
            return False


_ALL_TASK: dict[str, BackgroundStream] = dict()


def generate_task_id(kind: str, name: str | None = None) -> str:
    values = [kind]
    if name:
        values.append(name)
    base_id = '_'.join(values)

    # Ensure uniqueness by checking _ALL_TASK_NAMES
    task_id = base_id
    counter = 1
    while task_id in _ALL_TASK_NAMES:
        task_id = f"{base_id}_{counter}"
        counter += 1
    _ALL_TASK_NAMES.add(task_id)
    return task_id


def remove_task_id(task_id: str) -> BackgroundStream:
    """Remove a task_id from the global task names set.

    Args:
        task_id: The task identifier to remove.
    """
    try:
        _ALL_TASK_NAMES.discard(task_id)
        return _ALL_TASK.pop(task_id)
    except:
        pass
    return None


def add_task(task_id: str, stream: BackgroundStream) -> None:
    """Add a task to the global task registry.

    Args:
        task_id: Unique identifier for the task.
        stream: The BackgroundStream instance to manage (should already be started).
    """
    _ALL_TASK[task_id] = stream
    _ALL_TASK_NAMES.add(task_id)


def get_all_tasks():
    return _ALL_TASK


def join_task(task_id: str) -> bool:
    """Join a task and clean up its resources.

    Args:
        task_id: The task identifier to join.

    Returns:
        True if the task was found and joined, False otherwise.
    """
    if task_id not in _ALL_TASK:
        return False

    stream = _ALL_TASK.pop(task_id)
    stream.wait()
    _ALL_TASK_NAMES.discard(task_id)
    return True
