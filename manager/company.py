from .designer import Designer
from .programmer import Programmer
from .base import Worker, get_worker, add_worker, get_all_workers, execute_all_jobs
_designer = Designer('designer')
_programmer = Programmer('programmer')
