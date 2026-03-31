import dbm
import json
from pathlib import Path


class Job:
    def __init__(self):
        self.steps = list()
        self.target = str()
        self.skills = list()

    def serialize(self) -> str:
        """Serialize job to JSON string."""
        if not isinstance(self.target, str):
            raise TypeError(
                f"target must be a string, got {type(self.target).__name__}")
        for i, step in enumerate(self.steps):
            if not isinstance(step, str):
                raise TypeError(
                    f"step at index {i} must be a string, got {type(step).__name__}")
        for i, skill in enumerate(self.skills):
            if not isinstance(skill, str):
                raise TypeError(
                    f"skill at index {i} must be a string, got {type(skill).__name__}")
        return json.dumps({"steps": self.steps, "target": self.target, "skills": self.skills})

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
        for i, s in enumerate(steps):
            if not isinstance(s, str):
                raise Exception('All items in "steps" must be strings')
        
        # Validate target
        target = json_dict.get("target")
        if target is None:
            raise Exception('Missing required field "target"')
        if not isinstance(target, str):
            raise Exception('"target" must be a string')
        
        # Validate skills (optional)
        skills = json_dict.get("skills")
        if skills is not None:
            if not isinstance(skills, list):
                raise Exception('"skills" must be a list')
            for i, s in enumerate(skills):
                if not isinstance(s, str):
                    raise Exception('All items in "skills" must be strings')

    @classmethod
    def deserialize(cls, data: str) -> "Job":
        """Deserialize JSON string to Job object."""
        obj = cls()
        parsed = json.loads(data)
        Job.check_json_dict_validate(parsed)
        obj.steps = parsed.get("steps", [])
        obj.target = parsed.get("target", "")
        obj.skills = parsed.get("skills", [])
        return obj


class Worker:
    def __init__(self, name: str):
        self._db_path = name + ".db"

    def get_job(self, job_name: str):
        """Load a single job from database."""
        try:
            with dbm.open(str(self._db_path), 'c') as db:
                key = job_name.encode('utf-8')
                data = db.get(key)
                if data is not None:
                    # data format: "path\x00finished" where finished is '0' or '1'
                    path, finished = data.decode('utf-8').split('\x00')
                    # Read json from path, deserialize to job
                    with open(path, 'r', encoding='utf-8') as f:
                        job = Job.deserialize(f.read())
                    return job, finished == '1'
        except Exception:
            pass
        return None, True

    def _get_job_path(self, job_name: str):
        """Load a single job from database."""
        try:
            with dbm.open(str(self._db_path), 'c') as db:
                key = job_name.encode('utf-8')
                data = db.get(key)
                if data is not None:
                    # data format: "path\x00finished" where finished is '0' or '1'
                    path, finished = data.decode('utf-8').split('\x00')
                    return path, finished
        except Exception:
            pass
        return None, True

    def _save_job(self, job_name: str, path: str, finished: bool) -> None:
        """Save a single job to database."""
        try:
            with dbm.open(str(self._db_path), 'c') as db:
                key = job_name.encode('utf-8')
                # data format: "path\x00finished" where finished is '0' or '1'
                value = f"{path}\x00{int(finished)}"
                db[key] = value.encode('utf-8')
        except Exception:
            pass

    def add_job(self, job_name: str, job: Job):
        # Serialize job, save to job_path
        job_path = f"{job_name}.json"
        with open(job_path, 'w', encoding='utf-8') as f:
            f.write(job.serialize())
        # Save to database: job_name -> [path, False]
        self._save_job(job_name, job_path, False)

    def mark_finished(self, job_name: str):
        # Update job status to True in database
        job = self._get_job_path(job_name)
        if job is not None:
            self._save_job(job_name, job[0], True)

    def get_all_jobs(self) -> dict[str, list]:
        """Get all jobs from database.

        Returns:
            A dictionary mapping job_name -> [path, finished]
        """
        jobs = {}
        try:
            with dbm.open(str(self._db_path), 'c') as db:
                for key in db.keys():
                    job_name = key.decode('utf-8')
                    data = db[key].decode('utf-8')
                    path, finished = data.split('\x00')
                    jobs[job_name] = [path, finished == '1']
        except Exception:
            pass
        return jobs


_workers = dict()


def add_worker(worker_name: str, worker: Worker):
    _workers[worker_name] = worker


def get_worker(worker_name: str):
    return _workers.get(worker_name)
