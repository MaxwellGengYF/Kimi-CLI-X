_designer = None
_programmer = None


def create_company(
    designer_folder='designer',
    programmer_folder='programmer',
    ask_mode=False,
    clear_db=False
):
    from .designer import Designer
    from .programmer import Programmer
    global _programmer, _designer
    import manager.base as base
    _designer = Designer(designer_folder, clear_db)
    _programmer = Programmer(programmer_folder, clear_db)
    base._ask_mode = ask_mode


_temp_idx = 0


def schedule_project(content: str, job_name: str = None):
    from agent_utils import print_error
    if _designer is None or _programmer is None:
        print_error('Company not opened.')
        return
    from my_tools.common import _export_to_temp_file
    file_name, new_id = _export_to_temp_file(None, content)
    from .base import get_worker
    worker = get_worker('designer')
    if worker is None:
        print_error('Designer is not ready.')
        return
    global _temp_idx
    if job_name is None:
        job_name = f'job_{_temp_idx}'
        _temp_idx += 1
    worker.add_job(job_name, file_name)


def start_work():
    from .base import execute_all_jobs
    execute_all_jobs()


def do_job(job_json_path: str):
    from agent_utils import print_error
    if _programmer is None:
        print_error('Company not opened.')
        return
    _programmer.work(job_json_path)