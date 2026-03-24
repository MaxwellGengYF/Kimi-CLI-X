"""Shared state for process management tools."""
import subprocess
import threading
import queue
from typing import Optional


# Global state for process management
stdout_lines: list[str] = []
output_queue: queue.Queue = queue.Queue()
reader_thread: Optional[threading.Thread] = None
process: Optional[subprocess.Popen] = None
