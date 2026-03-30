import dbm
from pathlib import Path


class Worker:
    def __init__(self, name: str):
        self._db_path = name + ".db"

    def _get_job(self, job_name: str) -> list | None:
        """Load a single job from database."""
        try:
            with dbm.open(str(self._db_path), 'c') as db:
                key = job_name.encode('utf-8')
                data = db.get(key)
                if data is not None:
                    # data format: "path\x00finished" where finished is '0' or '1'
                    path, finished = data.decode('utf-8').split('\x00')
                    return [path, finished == '1']
        except Exception:
            pass
        return None

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

    def add_job(self, job_name: str, job_path: str):
        # Save to database: job_name -> [path, False]
        self._save_job(job_name, job_path, False)

    def mark_finished(self, job_name: str):
        # Update job status to True in database
        job = self._get_job(job_name)
        if job is not None:
            self._save_job(job_name, job[0], True)

    def get_job(self, job_name: str):
        v = self._get_job(job_name)
        if v is not None:
            return v[0], v[1]
        return None, True

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
