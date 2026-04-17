from pathlib import Path
from .base import Job
_designer = None


def create_company(
    designer_folder='designer',
    ask_mode=False,
    clear_db=False
):
    from .designer import Designer
    global _designer
    import kimix_manager.base as base
    _designer = Designer(designer_folder, clear_db)
    base._ask_mode = ask_mode


_temp_idx = 0


def schedule_project(content: str, job_name: str = None):
    from kimix.agent_utils import print_error
    if _designer is None:
        print_error('Company not opened.')
        return
    from my_tools.common import _export_to_temp_file
    file_name, new_id = _export_to_temp_file(None, content.strip(), '.md')
    from .base import get_worker
    worker = get_worker()
    if worker is None:
        print_error('Designer is not ready.')
        return
    global _temp_idx
    if job_name is None:
        job_name = f'job_{_temp_idx}'
        _temp_idx += 1
    worker.add_job(job_name, file_name)


def start_work():
    from .base import execute_all_jobs, get_all_workers
    execute_all_jobs()
    for v in get_all_workers():
        v.clear_db()


def designer(content: str) -> Path | None:
    from kimix.agent_utils import print_error
    if _designer is None:
        print_error('Company not opened.')
        return
    from my_tools.common import _export_to_temp_file
    file_path, new_id = _export_to_temp_file(None, content.strip())
    return _designer._work_designer(file_path, True)


def worker(job: Job):
    from kimix.agent_utils import print_error
    if _designer is None:
        print_error('Company not opened.')
        return
    _designer._work_programmer(job)
