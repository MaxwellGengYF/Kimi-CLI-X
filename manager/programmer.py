from pathlib import Path

from manager.base import Worker, Job, add_worker
from kimi_utils import prompt, create_session, close_session, validate
from agent_utils import run_thread, print_error


class Programmer:
    def __init__(self, folder: str):
        self._folder = Path(folder)
        self._folder.mkdir(exist_ok=True)
        self._worker = Worker(str(self._folder / "worker"),
                              lambda x: self.work(x))
        add_worker('programmer', self._worker)

    def work(self, job_path: str):
        session = None
        verify_session = None
        try:
            job = Job.deserialize(Path(job_path).read_text(encoding='utf-8'))
            # Create session for processing steps
            session = create_session()

            # Build skill prefix from skills array
            skill_prefix = ""
            dir_prefix = ''
            if job.skills:
                skill_list = ", ".join([f"skill:{s}" for s in job.skills])
                skill_prefix = f"use {skill_list}.\n"
            if job.directory:
                dir_prefix += f"in dir:{job.directory}"
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
                    f"write a test-case to verify and fix: {job.target}"
                prompt(verify_prompt, session=verify_session)
                verify_prompt = dir_prefix + 'run test to verify and fix error, check if all test cases pass'
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
