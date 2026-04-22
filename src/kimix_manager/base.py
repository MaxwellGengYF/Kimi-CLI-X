import json
import re
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from kimix.base import print_error, get_skill_dirs, run_thread

_ask_mode = False


def check_path_format(path: str) -> bool:
    """Check if a path's format is valid.

    Args:
        path: The path string to validate.

    Returns:
        True if the path format is valid, False otherwise.
    """
    if not isinstance(path, str):
        return False
    if not path or path.isspace():
        return False

    # Check for invalid characters in Windows paths
    # Invalid chars: < > : " | ? *
    invalid_chars = '<>"|?*'
    for char in invalid_chars:
        if char in path:
            return False

    # Check for reserved Windows device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    reserved_names = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                      'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3',
                      'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}

    # Get the base name without extension
    base_name = Path(path).stem.upper()
    if base_name in reserved_names:
        return False

    # Check for trailing spaces or dots (invalid in Windows)
    stripped = path.rstrip()
    if stripped.endswith('.') or stripped.endswith(' '):
        return False

    return True


class Job:
    def __init__(self):
        self.steps = list()
        self.target = str()
        self.skills = list()
        self.directory = str()

    def serialize(self) -> str:
        """Serialize job to JSON string."""
        for i, step in enumerate(self.steps):
            if not isinstance(step, str):
                raise TypeError(
                    f"step at index {i} must be a string, got {type(step).__name__}")
        result = {"steps": self.steps}
        if self.target:
            result["target"] = self.target
        if self.skills:
            for i, skill in enumerate(self.skills):
                if not isinstance(skill, str):
                    raise TypeError(
                        f"skill at index {i} must be a string, got {type(skill).__name__}")
            result["skills"] = self.skills
        if self.directory:
            result["directory"] = self.directory
        return json.dumps(result)

    @staticmethod
    def check_json_dict_validate(json_dict: dict):
        if not isinstance(json_dict, dict):
            raise Exception("JSON root must be an object")

        # Validate steps
        steps = json_dict.get("steps")
        if steps is None:
            raise Exception('Missing required field "steps"')
        if not isinstance(steps, list):
            raise Exception('"steps" must be a list')
        for s in steps:
            if not isinstance(s, str):
                raise Exception('All items in "steps" must be strings')

        # Validate target (optional)
        target = json_dict.get("target")
        if target is not None and not isinstance(target, str):
            raise Exception('"target" must be a string')

        # Validate skills (optional)
        skills = json_dict.get("skills")
        sk_dirs = get_skill_dirs()
        if skills is not None:
            if not isinstance(skills, list):
                raise Exception('"skills" must be a list')
            for s in skills:
                if not isinstance(s, str):
                    raise Exception('All items in "skills" must be strings')
                # Check if the skill exists in any skill_dir
                skill_found = False
                if sk_dirs:
                    for sk_dir in sk_dirs:
                        skill_path = Path(str(sk_dir)) / s / "SKILL.md"
                        if skill_path.exists():
                            skill_found = True
                            break
                if sk_dirs and not skill_found:
                    raise Exception(
                        f'Skill "{s}" does not exist in skill directory')

        # Validate directory (optional)
        directory = json_dict.get("directory")
        if directory is not None:
            if not isinstance(directory, str):
                raise Exception('"directory" must be a string')
            if not check_path_format(directory):
                raise Exception(
                    f'"directory" has invalid path format: "{directory}"')

    @classmethod
    def deserialize(cls, data: str) -> "Job":
        """Deserialize JSON string to Job object."""
        obj = cls()
        parsed = json.loads(data)
        Job.check_json_dict_validate(parsed)
        obj.steps = parsed.get("steps", [])
        obj.target = parsed.get("target", "")
        obj.skills = parsed.get("skills", [])
        obj.directory = parsed.get("directory", "")
        return obj


class Worker:
    def __init__(self, name: str, task, clear_db=False):
        self._db_path = Path(name + ".db")
        self._db = {}
        if clear_db:
            self.clear_db()
        else:
            self._load_db()
        self._task = task
        self._mutex = threading.Lock()

    def _load_db(self):
        """Load database from JSON file."""
        json_path = self._db_path / '.worker.json'
        try:
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    self._db = json.load(f)
        except Exception:
            self._db = {}

    def _save_db(self):
        """Save database to JSON file."""
        json_path = self._db_path / '.worker.json'
        try:
            self._db_path.mkdir(parents=True, exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self._db, f, ensure_ascii=False)
        except Exception as e:
            print_error(str(e))

    def clear_db(self):
        self._db = {}
        json_path = self._db_path / '.worker.json'
        try:
            if json_path.exists():
                json_path.unlink()
        except Exception:
            pass

    def get_job(self, job_name: str):
        """Load a single job from database."""
        try:
            with self._mutex:
                path = self._db.get(job_name)
                if path is not None:
                    # Read json from path, deserialize to job
                    with open(path, 'r', encoding='utf-8') as f:
                        job = Job.deserialize(f.read())
                    return job
        except Exception:
            pass
        return None

    def _get_job_path(self, job_name: str):
        """Load a single job from database."""
        try:
            with self._mutex:
                return self._db.get(job_name)
        except Exception:
            pass
        return None

    def _save_job(self, job_name: str, path) -> None:
        """Save a single job to database."""
        if type(path) is not str:
            path = str(path)
        try:
            with self._mutex:
                self._db[job_name] = path
                self._save_db()
        except Exception as e:
            print_error(str(e))

    def add_job(self, job_name: str, job):
        if type(job_name) is not str:
            job_name = str(job_name)
        # Serialize job, save to job_path
        if type(job) == Job:
            job_path = f"{job_name}.json"
            with open(job_path, 'w', encoding='utf-8') as f:
                f.write(job.serialize())
        else:
            job_path = job
        # Save to database: job_name -> path
        self._save_job(job_name, job_path)

    def get_all_jobs(self) -> dict[str, str]:
        with self._mutex:
            return self._db.copy()

    def execute_jobs(self):
        """Extract and remove all jobs in database, and call self._task with value.

        Returns:
            int: Number of jobs executed.
        """
        jobs_executed = 0
        try:
            # Extract all jobs under mutex
            jobs_data = []
            with self._mutex:
                jobs_data = list(self._db.values())
                self._db.clear()
                self._save_db()

            # Process jobs outside of mutex
            thds: list[threading.Thread] = []
            for data in jobs_data:
                thds.append(run_thread(lambda: self._task(data)))
                jobs_executed += 1
            for i in thds:
                i.join()
        except Exception as e:
            print_error()

        return jobs_executed

    def has_jobs(self) -> bool:
        """Check if there are any jobs in the database."""
        with self._mutex:
            return len(self._db) > 0


_workers: deque[Worker] = deque()
_workers_mutex = threading.Lock()


def add_worker(worker: Worker):
    with _workers_mutex:
        _workers.append(worker)


def get_worker() -> Worker | None:
    """Get a worker using ring-queue design (dequeue from left, enqueue to right)."""
    with _workers_mutex:
        if not _workers:
            return None
        worker = _workers.popleft()
        _workers.append(worker)
        return worker


def get_all_workers() -> list[Worker]:
    """Get a copy of all workers."""
    with _workers_mutex:
        return list(_workers)


def execute_all_jobs():
    """Concurrently call all workers' execute_jobs, looping until no job in any worker.

    This function spawns a thread for each worker and continuously calls execute_jobs
    on each worker until all workers report no more jobs.
    """
    def worker_loop(worker: Worker):
        """Continuously execute jobs from a worker until no jobs remain."""
        while True:
            jobs_executed = worker.execute_jobs()
            if jobs_executed == 0:
                break

    # Keep looping until no jobs in any worker
    while True:
        workers = get_all_workers()
        if not workers:
            break

        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = {
                executor.submit(worker_loop, worker): i
                for i, worker in enumerate(workers)
            }

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    print_error()
        # Check if any worker still has jobs (including newly added workers)
        has_any_jobs = False
        for worker in get_all_workers():
            if worker.has_jobs():
                has_any_jobs = True
                break
        if not has_any_jobs:
            break
