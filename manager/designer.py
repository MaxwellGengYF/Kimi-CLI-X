import json
from pathlib import Path
import os

from manager.base import Worker, get_worker, Job, add_worker
from kimi_utils import prompt, create_session, close_session, validate
from agent_utils import print_error, _get_skill_dirs, print_warning, print_success
from my_tools.check_fmt import check_json


class Designer:
    def __init__(self, folder: str, clear=False):
        self._folder = Path(folder)
        self._folder.mkdir(exist_ok=True)
        self._worker = Worker(str(self._folder / "worker"),
                              lambda x: self.work(x), clear)
        add_worker(self._worker)

    def _work_designer(self, requirement_file_name: str):
        """Designer branch: Process requirement file and create job JSON."""
        # Sanitize the filename to ensure it's valid
        file_path = Path(requirement_file_name)
        dst_file_path = self._folder / \
            Path(str(file_path.with_suffix('')) + '__task.json')
        dst_file_path.parent.mkdir(exist_ok=True)
        if dst_file_path.exists():
            os.remove(dst_file_path)
        if not file_path.exists():
            print(f"Error: File {file_path} not found.")
            return
        skill_dirs = _get_skill_dirs()
        if skill_dirs:
            skill_dirs_str = ', '.join([str(d) for d in skill_dirs])
            skill_dir = f"* The proper skills under '{skill_dirs_str}', to 'skills'\n"
        else:
            skill_dir = ''
        prompt_text = f'''
Analyze the following requirement file: '{str(file_path)}'.
Design todo-list prompts to finish the requirement. (may split to multiple steps)
Write to JSON file '{dst_file_path}' with these:
* The prompt steps to 'steps'.
* A directory to work on this requirement (use relative path, make proper name), to 'directory'
* The way to validate if the requirement implemented properly to 'target'.
{skill_dir}
The file's format should be:
```
{{
"steps": ["step1", "step2"],
"target": "way to ...", // optional
"directory": "directory path", // optional
"skills": ["skill1", "skill2"]  // optional
}}
```
'''

        max_try_time = 3
        session = None
        try:
            session = create_session(agent_file='agent_boss.yaml')
            for i in range(max_try_time):
                import my_tools.flag as flag
                flag.reset_flag()
                prompt(prompt_text, session=session)
                err_msg = check_json(
                    dst_file_path, Job.check_json_dict_validate)
                if not err_msg:
                    break
                elif i < max_try_time - 1:
                    print_warning(err_msg)
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
        import manager.base as base
        if base._ask_mode:
            print_success(
                f'File saved to {dst_file_path}, do you want me to ask programmer to work?(y/n)')
            v = input('').lower()
            if not (v == 'y' or v == 'yes'):
                return
        worker: Worker = get_worker()
        if worker:
            worker.add_job(file_path, dst_file_path)
        else:
            print_error('Can not get worker')

    def _work_programmer(self, job: Job):
        """Programmer branch: Execute job steps."""
        session = None
        verify_session = None
        try:
            # Create session for processing steps
            session = create_session()

            # Build skill prefix from skills array
            skill_prefix = ""
            dir_prefix = ''
            if job.skills:
                skill_list = ", ".join([f"skill:{s}" for s in job.skills])
                skill_prefix = f"use {skill_list}.\n"
            if job.directory:
                dir_prefix += f"in dir `{job.directory}`\n"
            # Process all steps
            for step in job.steps:
                prompt_text = skill_prefix + dir_prefix + step
                prompt(prompt_text, session=session)

            # Close the processing session before starting verification
            close_session(session)
            session = None

            # Start a new session for verification using target
            if job.target:
                verify_session = create_session()
                verify_prompt = skill_prefix + dir_prefix + \
                    f"write a comprehensive, jumbo test file to verify this target and fix any error:\n```\n{job.target}\n```"
                if not validate(verify_prompt, session=verify_session):
                    verify_prompt = dir_prefix + \
                        'run test to verify and fix error, check if all test cases pass'
                    for i in range(3):
                        if validate(verify_prompt, session=session):
                            break

        except Exception as e:
            print_error(f"Error in programmer work: {str(e)}")
        finally:
            if session:
                close_session(session)
            if verify_session:
                close_session(verify_session)

    def _is_valid_job_json(self, data: str) -> bool:
        """Check if data is valid JSON that can be deserialized to a Job."""
        try:
            Job.deserialize(data)
            return True
        except (json.JSONDecodeError, Exception):
            return False

    def work(self, job_path: str):
        """
        Main work entry point.
        If job_path is valid JSON that serializes to a Job class, go programmer's branch.
        Otherwise, go designer's branch.
        """
        # Try to read as file first
        path_obj = Path(job_path)
        if path_obj.exists():
            try:
                content = path_obj.read_text(encoding='utf-8')
                if self._is_valid_job_json(content):
                    # Programmer branch: valid Job JSON file
                    job = Job.deserialize(content)
                    self._work_programmer(job)
                    return
            except Exception:
                pass
            # Designer branch: treat as requirement file
            self._work_designer(job_path)
        else:
            # Not a file, try parsing as JSON string directly
            if self._is_valid_job_json(job_path):
                # Programmer branch: valid Job JSON string
                job = Job.deserialize(job_path)
                self._work_programmer(job)
            else:
                # Designer branch: treat as requirement file path (will fail if not exists)
                self._work_designer(job_path)
