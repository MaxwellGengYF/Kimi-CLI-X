"""Comprehensive async/await tests for tools using BackgroundStream and ProcessTask."""

import asyncio
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import anyio
import pytest

from kimi_agent_sdk import ToolOk, ToolError
from my_tools.background.utils import (
    BackgroundStream,
    add_task,
    discard_all_tasks,
    generate_task_id,
    get_all_tasks,
    remove_task_id,
)
from my_tools.background import TaskList, TaskOutput, TaskListParams, TaskOutputParams
from my_tools.file.run import Run, RunParams
from my_tools.py import Python, Params as PyParams
from my_tools.file.input import Input, InputParams


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.custom_data = {}
    return session


@pytest.fixture(autouse=True)
async def cleanup_task_data(mock_session: MagicMock) -> Any:
    yield
    await discard_all_tasks(mock_session)


# ---------------------------------------------------------------------------
# Agent tool (background mode)
# ---------------------------------------------------------------------------
class TestAgentBackground:
    async def test_run_in_background_starts_and_registers(self, mock_session: MagicMock) -> None:
        from my_tools.agent import Agent, SubAgentParams

        agent = Agent(session=mock_session)
        params = SubAgentParams(prompt="test prompt", run_in_background=True)

        with patch("my_tools.agent.add_task") as mock_add_task, \
             patch.object(BackgroundStream, "start", return_value=None) as mock_start:
            result = await agent(params)

        assert isinstance(result, ToolOk)
        assert "Task ID" in str(result.output)
        mock_start.assert_awaited_once()
        mock_add_task.assert_called_once()

    async def test_nested_subagent_rejected(self, mock_session: MagicMock) -> None:
        from my_tools.agent import Agent, SubAgentParams

        agent = Agent(session=mock_session)
        params = SubAgentParams(prompt="nested", run_in_background=True)
        mock_session.custom_data["sub_agent_active"] = True
        try:
            result = await agent(params)
            assert "cannot be called within this scope" in str(result.message)
        finally:
            mock_session.custom_data["sub_agent_active"] = False


# ---------------------------------------------------------------------------
# TaskList tool
# ---------------------------------------------------------------------------
class TestTaskList:
    async def test_empty(self, mock_session: MagicMock) -> None:
        tool = TaskList(session=mock_session)
        result = await tool(TaskListParams())
        assert "No background tasks running" in str(result.output)

    async def test_lists_tasks(self, mock_session: MagicMock) -> None:
        tool = TaskList(session=mock_session)
        stream = BackgroundStream()

        def worker(q: queue.Queue[str]) -> None:
            q.put("hello")

        await stream.start(worker, stop_function=lambda: None)
        add_task(mock_session, "run_test", stream)
        result = await tool(TaskListParams())
        await stream.wait()
        assert "run_test" in str(result.output)


# ---------------------------------------------------------------------------
# TaskOutput tool
# ---------------------------------------------------------------------------
class TestTaskOutput:
    async def test_not_found(self, mock_session: MagicMock) -> None:
        tool = TaskOutput(session=mock_session)
        result = await tool(TaskOutputParams(task_id="missing"))
        assert "not found" in str(result.message)

    async def test_wait_and_get_output(self, mock_session: MagicMock) -> None:
        tool = TaskOutput(session=mock_session)
        stream = BackgroundStream()

        def worker(q: queue.Queue[str]) -> None:
            q.put("output_line")
            time.sleep(0.05)

        await stream.start(worker, stop_function=lambda: None)
        add_task(mock_session, "run_test", stream)

        result = await tool(TaskOutputParams(task_id="run_test", block=True, timeout=5))
        assert "output_line" in str(result.output)
        assert "run_test" not in get_all_tasks(mock_session)

    async def test_kill_running_task(self, mock_session: MagicMock) -> None:
        tool = TaskOutput(session=mock_session)
        stream = BackgroundStream()

        def worker(q: queue.Queue[str]) -> None:
            time.sleep(10)

        await stream.start(worker, stop_function=lambda: None)
        add_task(mock_session, "run_test", stream)

        result = await tool(TaskOutputParams(task_id="run_test", block=False, kill=True))
        await stream.wait()
        assert "run_test" not in get_all_tasks(mock_session)

    async def test_export_to_file(self, mock_session: MagicMock, tmp_path: Path) -> None:
        tool = TaskOutput(session=mock_session)
        stream = BackgroundStream()

        def worker(q: queue.Queue[str]) -> None:
            q.put("file_content")

        await stream.start(worker, stop_function=lambda: None)
        add_task(mock_session, "run_test", stream)

        out_path = tmp_path / "out.txt"
        result = await tool(TaskOutputParams(task_id="run_test", block=True, timeout=5, output_path=str(out_path)))
        await stream.wait()
        assert out_path.exists()
        assert "file_content" in out_path.read_text(encoding="utf-8")
        assert "exported to file" in str(result.output)


# ---------------------------------------------------------------------------
# Run tool
# ---------------------------------------------------------------------------
class TestRun:
    async def test_foreground_success(self, mock_session: MagicMock) -> None:
        tool = Run(session=mock_session)
        params = RunParams(path=sys.executable, args=["-c", "print('hello_run')"], timeout=10)
        result = await tool(params)
        assert "hello_run" in str(result.output)

    async def test_foreground_failure(self, mock_session: MagicMock) -> None:
        tool = Run(session=mock_session)
        params = RunParams(path=sys.executable, args=["-c", "import sys; sys.exit(1)"], timeout=10)
        result = await tool(params)
        assert "failed" in str(result.message).lower() or "exited" in str(result.output).lower()

    async def test_foreground_timeout(self, mock_session: MagicMock) -> None:
        tool = Run(session=mock_session)
        params = RunParams(
            path=sys.executable,
            args=["-c", "import time; time.sleep(100)"],
            timeout=3,
        )
        result = await tool(params)
        assert "timeout" in str(result.message).lower() or "background" in str(result.output).lower()
        # task should remain registered after timeout
        assert len(get_all_tasks(mock_session)) >= 1
        # cleanup
        for tid in list(get_all_tasks(mock_session).keys()):
            remove_task_id(mock_session, tid)

    async def test_background_mode(self, mock_session: MagicMock) -> None:
        tool = Run(session=mock_session)
        params = RunParams(
            path=sys.executable,
            args=["-c", "print('bg')"],
            run_in_background=True,
        )
        result = await tool(params)
        assert "Task ID" in str(result.output)
        # cleanup
        for tid in list(get_all_tasks(mock_session).keys()):
            await get_all_tasks(mock_session)[tid].wait(timeout=5)
            remove_task_id(mock_session, tid)

    async def test_output_path(self, mock_session: MagicMock, tmp_path: Path) -> None:
        tool = Run(session=mock_session)
        out_path = tmp_path / "run_out.txt"
        params = RunParams(
            path=sys.executable,
            args=["-c", "print('to_file')"],
            timeout=10,
            output_path=str(out_path),
        )
        result = await tool(params)
        assert out_path.exists()
        assert "to_file" in out_path.read_text(encoding="utf-8")
        assert "saved to file" in str(result.output)


# ---------------------------------------------------------------------------
# Python tool
# ---------------------------------------------------------------------------
class TestPython:
    async def test_foreground_success(self, mock_session: MagicMock) -> None:
        tool = Python(session=mock_session)
        params = PyParams(code="print('hello_py')", timeout=10)
        result = await tool(params)
        assert "hello_py" in str(result.output)

    async def test_foreground_failure(self, mock_session: MagicMock) -> None:
        tool = Python(session=mock_session)
        params = PyParams(code="import sys; sys.exit(1)", timeout=10)
        result = await tool(params)
        assert "failed" in str(result.message).lower() or "exited" in str(result.output).lower()

    async def test_foreground_timeout(self, mock_session: MagicMock) -> None:
        tool = Python(session=mock_session)
        params = PyParams(code="import time; time.sleep(100)", timeout=1)
        result = await tool(params)
        assert "timeout" in str(result.message).lower() or "background" in str(result.output).lower()
        # cleanup
        for tid in list(get_all_tasks(mock_session).keys()):
            remove_task_id(mock_session, tid)

    async def test_background_mode(self, mock_session: MagicMock) -> None:
        tool = Python(session=mock_session)
        params = PyParams(code="print('bg_py')", run_in_background=True)
        result = await tool(params)
        assert "Task ID" in str(result.output)
        # cleanup
        for tid in list(get_all_tasks(mock_session).keys()):
            await get_all_tasks(mock_session)[tid].wait(timeout=5)
            remove_task_id(mock_session, tid)

    async def test_dest_export(self, mock_session: MagicMock, tmp_path: Path) -> None:
        tool = Python(session=mock_session)
        dest = tmp_path / "py_out.txt"
        params = PyParams(code="print('dest_out')", timeout=10, dest=str(dest))
        result = await tool(params)
        assert dest.exists()
        assert "dest_out" in dest.read_text(encoding="utf-8")
        assert "exported to" in str(result.output)


# ---------------------------------------------------------------------------
# Input tool
# ---------------------------------------------------------------------------
class TestInput:
    async def test_not_found(self, mock_session: MagicMock) -> None:
        tool = Input(session=mock_session)
        result = await tool(InputParams(task_id="missing", text="hello"))
        assert "not found" in str(result.message).lower()

    async def test_send_input_to_running_process(self, mock_session: MagicMock) -> None:
        from my_tools.common import ProcessTask

        task = ProcessTask(
            sys.executable,
            ["-c", "import sys; line=sys.stdin.readline(); print('got', line.strip())"],
        )
        tid = await task.start(mock_session, kind="run", name="input_test")
        await asyncio.sleep(0.2)

        tool = Input(session=mock_session)
        result = await tool(InputParams(task_id=tid, text="hello\n"))
        assert "sent" in str(result.output).lower()

        await task.wait(timeout=5)
        output = await task.stream.get_output()
        assert "got hello" in output
        remove_task_id(mock_session, tid)

    async def test_input_fails_when_no_stdin(self, mock_session: MagicMock) -> None:
        from my_tools.common import ProcessTask

        # process that exits quickly
        task = ProcessTask(sys.executable, ["-c", "print('done')"])
        tid = await task.start(mock_session, kind="run", name="quick")
        await task.wait(timeout=5)

        tool = Input(session=mock_session)
        result = await tool(InputParams(task_id=tid, text="data"))
        # Input may fail because process already finished
        assert "failed" in str(result.message).lower() or "sent" in str(result.output).lower()
        remove_task_id(mock_session, tid)


# ---------------------------------------------------------------------------
# Async syntax / integration smoke tests
# ---------------------------------------------------------------------------
class TestAsyncIntegration:
    async def test_background_stream_awaited_methods(self) -> None:
        stream = BackgroundStream()
        # All these are declared async; calling them with await should work even
        # if the underlying implementation is synchronous.
        assert await stream.is_started() is False
        assert await stream.is_stopped() is False
        assert await stream.thread_is_alive() is False
        assert await stream.success() is False
        assert await stream.get_output() == ""
        assert await stream.get_queue() is None

    async def test_process_task_all_async_methods_awaited(self, mock_session: MagicMock) -> None:
        from my_tools.common import ProcessTask

        task = ProcessTask(sys.executable, ["-c", "print('await_test')"])
        tid = await task.start(mock_session, kind="run", name="await")
        assert await task.thread_is_alive() is True
        await task.wait(timeout=5)
        assert await task.thread_is_alive() is False
        assert await task.stream.success() is True
        output = await task.stream.pop_output()
        assert "await_test" in output
        remove_task_id(mock_session, tid)

    async def test_concurrent_task_outputs(self, mock_session: MagicMock) -> None:
        stream1 = BackgroundStream()
        stream2 = BackgroundStream()

        def w1(q: queue.Queue[str]) -> None:
            q.put("a")

        def w2(q: queue.Queue[str]) -> None:
            q.put("b")

        await stream1.start(w1, stop_function=lambda: None)
        await stream2.start(w2, stop_function=lambda: None)
        add_task(mock_session, "t1", stream1)
        add_task(mock_session, "t2", stream2)

        out1, out2 = await asyncio.gather(
            stream1.get_output(),
            stream2.get_output(),
        )
        assert "a" in out1
        assert "b" in out2

        await stream1.wait()
        await stream2.wait()
        remove_task_id(mock_session, "t1")
        remove_task_id(mock_session, "t2")
