# -*- coding: utf-8 -*-
"""Kimix server process lifecycle management.

Each workspace path maps to one kimix server process and one port.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_STATE_FILE = Path("data/kimix_bot/state/sessions.json")
_DEFAULT_LOG_DIR = Path("data/kimix_bot/kimix_logs")
_STARTUP_TIMEOUT_SEC = 30
_HEALTH_POLL_INTERVAL = 1


class ProcessStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ManagedProcess:
    path: str
    port: int
    ws_port: Optional[int] = None
    pid: Optional[int] = None
    status: ProcessStatus = ProcessStatus.STOPPED
    session_id: Optional[str] = None
    started_at: Optional[str] = None
    last_error: Optional[str] = None
    chat_id: Optional[str] = None

    _process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _stdout_log: Optional[Any] = field(default=None, repr=False)
    _stderr_log: Optional[Any] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "port": self.port,
            "ws_port": self.ws_port,
            "pid": self.pid,
            "status": self.status.value,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_error": self.last_error,
            "chat_id": self.chat_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManagedProcess":
        proc = cls(
            path=data.get("path", ""),
            port=data.get("port", 0),
            ws_port=data.get("ws_port"),
            pid=data.get("pid"),
            session_id=data.get("session_id"),
            started_at=data.get("started_at"),
            last_error=data.get("last_error"),
            chat_id=data.get("chat_id"),
        )
        try:
            proc.status = ProcessStatus(data.get("status", "stopped"))
        except ValueError:
            proc.status = ProcessStatus.STOPPED
        return proc

    @property
    def is_alive(self) -> bool:
        if not self.port:
            return False
        return _port_open(self.port)


class KimixProcessManager:
    """Kimix server process lifecycle manager."""

    def __init__(
        self,
        base_port: int = 8896,
        state_file: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        startup_timeout: int = _STARTUP_TIMEOUT_SEC,
        projects: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.base_port = base_port
        self._state_file = state_file or _DEFAULT_STATE_FILE
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._startup_timeout = startup_timeout
        self._projects: List[Dict[str, Any]] = projects or []
        self._processes: Dict[str, ManagedProcess] = {}
        self._lock = threading.Lock()
        self._load_state()

    def ensure_running(
        self,
        path: str,
        chat_id: Optional[str] = None,
    ) -> Tuple[bool, ManagedProcess, str]:
        resolved = self._resolve_path(path)
        if resolved is None:
            dummy = ManagedProcess(path=path, port=0)
            dummy.status = ProcessStatus.ERROR
            dummy.last_error = f"路径不存在或无效: {path}"
            return False, dummy, dummy.last_error

        path = resolved
        with self._lock:
            proc = self._processes.get(path)
            if proc and proc.is_alive:
                proc.status = ProcessStatus.RUNNING
                return True, proc, f"已在端口 {proc.port} 运行"

            port = self._allocate_port()
            ws_port = port + 1
            if proc is None:
                proc = ManagedProcess(path=path, port=port, ws_port=ws_port, chat_id=chat_id)
                self._processes[path] = proc
            else:
                proc.port = port
                proc.ws_port = ws_port
                proc.session_id = None

        return self._start_process(proc)

    def stop(self, path: str) -> Tuple[bool, str]:
        resolved = self._resolve_path(path, must_exist=False)
        path = resolved or path
        with self._lock:
            proc = self._processes.get(path)
            if not proc:
                return False, f"未找到 {path} 的进程"

            self._kill_process(proc)
            proc.status = ProcessStatus.STOPPED
            proc.pid = None
            proc.session_id = None
            self._save_state()
            logger.info("[ProcessManager] 已停止: %s", path)
            return True, "已停止"

    def stop_all(self) -> int:
        count = 0
        for path in list(self._processes.keys()):
            ok, _ = self.stop(path)
            if ok:
                count += 1
        return count

    def list_processes(self) -> List[ManagedProcess]:
        return list(self._processes.values())

    def get_status_text(self) -> str:
        if not self._processes:
            return "当前无 kimix 进程。"
        lines = ["=== Kimix 进程状态 ==="]
        for proc in self._processes.values():
            alive = proc.is_alive
            icon = (
                "🟢" if alive
                else {"stopped": "⚪", "starting": "🟡", "error": "🔴"}.get(
                    proc.status.value, "⚪"
                )
            )
            lines.append(
                f"{icon} {Path(proc.path).name}  port={proc.port}  ws={proc.ws_port or '-'}  pid={proc.pid or '-'}"
            )
            if proc.last_error:
                lines.append(f"   ⚠ {proc.last_error}")
        return "\n".join(lines)

    def find_by_slug(self, slug: str) -> Optional[str]:
        for p in self._projects:
            if p.get("slug") == slug or p.get("label", "").lower() == slug.lower():
                return p.get("path", "")
        return None

    def _start_process(
        self, proc: ManagedProcess
    ) -> Tuple[bool, ManagedProcess, str]:
        path = Path(proc.path)
        if not path.exists():
            proc.status = ProcessStatus.ERROR
            proc.last_error = f"路径不存在: {proc.path}"
            return False, proc, proc.last_error

        self._log_dir.mkdir(parents=True, exist_ok=True)
        out_log_path = self._log_dir / f"kimix_{proc.port}.out.log"
        err_log_path = self._log_dir / f"kimix_{proc.port}.err.log"

        cmd = [
            "kimix",
            "serve",
            "--port", str(proc.port),
        ]
        kwargs: Dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            kwargs["shell"] = False

        logger.info("[ProcessManager] 启动: %s (cwd=%s)", " ".join(cmd), proc.path)

        try:
            stdout_fh = open(out_log_path, "w", encoding="utf-8")
            stderr_fh = open(err_log_path, "w", encoding="utf-8")
            process = subprocess.Popen(
                cmd, cwd=proc.path, stdout=stdout_fh, stderr=stderr_fh, **kwargs,
            )
            proc.pid = process.pid
            proc._process = process
            proc._stdout_log = stdout_fh
            proc._stderr_log = stderr_fh
            proc.status = ProcessStatus.STARTING
            proc.started_at = datetime.now().isoformat()
        except FileNotFoundError:
            proc.status = ProcessStatus.ERROR
            proc.last_error = "python/kimix 命令未找到。请确认已安装并在 PATH 中。"
            return False, proc, proc.last_error
        except Exception as exc:
            proc.status = ProcessStatus.ERROR
            proc.last_error = str(exc)
            return False, proc, proc.last_error

        for _ in range(self._startup_timeout):
            time.sleep(_HEALTH_POLL_INTERVAL)
            if _port_open(proc.port):
                proc.status = ProcessStatus.RUNNING
                self._save_state()
                msg = f"已启动 port={proc.port} ws={proc.ws_port} PID={proc.pid}"
                logger.info("[ProcessManager] %s", msg)
                return True, proc, msg

        self._kill_process(proc)
        proc.status = ProcessStatus.ERROR
        proc.last_error = (
            f"kimix server 在 {self._startup_timeout}s 内未就绪 "
            f"(port={proc.port})。请检查日志: {err_log_path}"
        )
        return False, proc, proc.last_error

    def _kill_process(self, proc: ManagedProcess) -> None:
        if proc._process:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc._process.pid), "/T", "/F"],
                        check=False, capture_output=True,
                    )
                else:
                    proc._process.terminate()
                try:
                    proc._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc._process.kill()
                    proc._process.wait(timeout=2)
            except Exception as exc:
                logger.warning("[ProcessManager] 终止进程异常: %s", exc)
            proc._process = None

        for fh in (proc._stdout_log, proc._stderr_log):
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
        proc._stdout_log = proc._stderr_log = None

    def _allocate_port(self) -> int:
        used = set()
        for p in self._processes.values():
            if p.port:
                used.add(p.port)
            if p.ws_port:
                used.add(p.ws_port)
        port = self.base_port
        while port in used or _port_open(port) or _port_open(port + 1):
            port += 2
        return port

    def _resolve_path(self, path: str, must_exist: bool = True) -> Optional[str]:
        if not path:
            return None
        lower = path.strip().lower()
        for p in self._projects:
            if p.get("slug", "").lower() == lower or p.get("label", "").lower() == lower:
                raw = p.get("path", "")
                if raw:
                    return self._resolve_path(raw, must_exist=must_exist)
        try:
            resolved = str(Path(path).expanduser().resolve())
            if must_exist and not Path(resolved).exists():
                return None
            return resolved
        except Exception:
            return None

    def _save_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = [p.to_dict() for p in self._processes.values()]
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error("[ProcessManager] 保存状态失败: %s", exc)

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            recovered = 0
            for item in data:
                path = item.get("path", "")
                port = item.get("port", 0)
                if not path or not port:
                    continue
                if _port_open(port):
                    proc = ManagedProcess.from_dict(item)
                    proc.status = ProcessStatus.RUNNING
                    self._processes[path] = proc
                    recovered += 1
                    continue

            if recovered:
                logger.info("[ProcessManager] 恢复 %d 个进程", recovered)
            self._save_state()
        except Exception as exc:
            logger.error("[ProcessManager] 加载状态失败: %s", exc)
            self._processes.clear()


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def extract_path_from_text(text: str, projects: List[Dict[str, str]]) -> Optional[str]:
    """Extract path from text (supports project slugs and absolute paths)."""
    import re
    text = text.strip()
    lower = text.lower()
    for p in projects:
        slug = p.get("slug", "")
        label = p.get("label", "")
        if slug and lower == slug.lower():
            return p.get("path", "")
        if label and lower == label.lower():
            return p.get("path", "")
    # Try matching individual tokens (e.g. "启动 rb" -> "rb")
    for token in lower.split():
        for p in projects:
            slug = p.get("slug", "")
            label = p.get("label", "")
            if slug and token == slug.lower():
                return p.get("path", "")
            if label and token == label.lower():
                return p.get("path", "")
    for pattern in [r"([~/][^\s]+)", r"([A-Z]:\\[^\s]+)", r"([A-Z]:/[^\s]+)"]:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None
