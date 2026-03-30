from pathlib import Path
import os

from manager.worker import Worker, get_worker
from kimi_utils import prompt, create_session, close_session
from agent_utils import run_thread, print_error


class Designer:
    def __init__(self, folder: str):
        self._folder = Path(folder)
        self._folder.mkdir(exist_ok=True)
        self._worker = Worker(str(self._folder / "worker"))

    def work(self, request: str):
        """Summarize the content of the request file using an Agent.

        Args:
            request: Path to the input file to summarize.
        """
        # Read the file content
        file_path = Path(request)
        dst_file_path = Path(str(Path(request).suffix('')) + '__exec.md')
        if dst_file_path.exists():
            os.remove(dst_file_path)
        if not file_path.exists():
            print(f"Error: File {request} not found.")
            return

        def async_func():
            prompt_text = f'''
Analyze the following requirement file: '{str(file_path)}'.
Design a todo-list prompt to finish the requirement. Write to '{dst_file_path}'
'''
            max_try_time = 3
            session = None
            try:
                session = create_session()
                for i in range(max_try_time):
                    prompt(prompt_text, session=session)
                    if dst_file_path.exists():
                        break
            finally:
                if session:
                    close_session(session)
            if not dst_file_path.exists():
                print_error(f'Failed to export {dst_file_path}.')
                return
            worker: Worker = get_worker('programmer')
            if worker:
                worker.add_job(request, dst_file_path)
            else:
                print_error('Can not get worker `programmer`')
        run_thread(async_func)
