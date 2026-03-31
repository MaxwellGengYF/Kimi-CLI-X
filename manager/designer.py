import re
from pathlib import Path
import os

from manager.worker import Worker, get_worker, Job, add_worker
from kimi_utils import prompt, create_session, close_session
from agent_utils import run_thread, print_error
from my_tools.check_fmt import check_json


def _sanitize_filename(name: str) -> str:
    # Replace invalid characters with underscore
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)

    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')

    # Check for reserved Windows names
    reserved = {'CON', 'PRN', 'AUX', 'NUL'}
    reserved.update(f'COM{i}' for i in range(1, 10))
    reserved.update(f'LPT{i}' for i in range(1, 10))

    # If name (without extension) is reserved, prefix with underscore
    name_without_ext = sanitized.split(
        '.')[0] if '.' in sanitized else sanitized
    if name_without_ext.upper() in reserved:
        sanitized = '_' + sanitized

    # Handle empty result
    if not sanitized:
        sanitized = 'unnamed'

    return sanitized


class Designer:
    def __init__(self, folder: str):
        self._folder = Path(folder)
        self._folder.mkdir(exist_ok=True)
        self._worker = Worker(str(self._folder / "worker"))
        add_worker('designer', self._worker)

    def work(self, requirement: str, require_name: str):
        # Sanitize the filename to ensure it's valid
        require_name = _sanitize_filename(require_name)
        # Read the file content
        file_path = self._folder / require_name
        file_path.write_text(requirement, encoding='utf-8')
        dst_file_path = Path(str(file_path.with_suffix('')) + '__task.json')
        dst_file_path.parent.mkdir(exist_ok=True)
        if dst_file_path.exists():
            os.remove(dst_file_path)
        if not file_path.exists():
            print(f"Error: File {require_name} not found.")
            return

        def async_func():
            prompt_text = f'''
Analyze the following requirement file: '{str(file_path)}'.
Design todo-list prompts to finish the requirement. (may split to multiple steps)
Write to JSON file '{dst_file_path}' with these:
* The prompt steps to 'steps'.
* The way to validate if the requirement implemented properly to 'target'.
* The proper skills may used for this requirement
The file's format should be:
```
{{
    "steps": ["step1", "step2"],
    "target": "way to ...",
    "skills": ["skill1", "skill2"]
}}
```
'''

            max_try_time = 3
            session = None
            try:
                session = create_session()
                for i in range(max_try_time):
                    import my_tools.flag as flag
                    flag.reset_flag()
                    prompt(prompt_text, session=session)
                    if not dst_file_path.exists():
                        prompt()
                    err_msg = check_json(
                        dst_file_path, Job.check_json_dict_validate)
                    if not err_msg:
                        break
                    elif i < max_try_time - 1:
                        print(err_msg)
                        prompt_text = f'''
In {dst_file_path} fix this: {err_msg}.
'''
                    else:
                        print_error(f'Write to {dst_file_path} failed.')
                        return
            finally:
                if session:
                    close_session(session)
            if not dst_file_path.exists():
                print_error(f'Failed to export {dst_file_path}.')
                return
            worker: Worker = get_worker('programmer')
            if worker:
                worker.add_job(require_name, dst_file_path)
            else:
                print_error('Can not get worker `programmer`')
        run_thread(async_func)
