"""Tests for SetTodoList tool in kimi_cli.tools.todo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from kimi_cli.tools.todo import SetTodoList, Params, Todo
from kimi_cli.tools.display import TodoDisplayBlock
from kosong.tooling import ToolReturnValue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_subagent_state(tmp_path: Path) -> Path:
    """Return a temporary directory that acts as a subagent instance dir."""
    state_dir = tmp_path / "subagent" / "test-agent"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


@pytest.fixture
def mock_runtime(tmp_subagent_state: Path) -> MagicMock:
    """Create a mock Runtime configured as a subagent with a real state file path."""
    store = MagicMock()
    store.instance_dir.return_value = tmp_subagent_state

    runtime = MagicMock()
    runtime.role = "subagent"
    runtime.subagent_store = store
    runtime.subagent_id = "test-agent"
    return runtime


@pytest.fixture
def tool(mock_runtime: MagicMock) -> SetTodoList:
    return SetTodoList(runtime=mock_runtime)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_state(state_dir: Path, todos: list[dict[str, str]]) -> None:
    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps({"todos": todos}, ensure_ascii=False), encoding="utf-8")


def _read_state(state_dir: Path) -> dict[str, Any]:
    state_file = state_dir / "state.json"
    if not state_file.exists():
        return {}
    return json.loads(state_file.read_text(encoding="utf-8"))


def _make_params(todos: list[Todo] | Todo | None, force_replace: bool = False) -> Params:
    return Params(todos=todos, force_replace=force_replace)


# ---------------------------------------------------------------------------
# 1. Incremental update (partial todo list, no error)
# ---------------------------------------------------------------------------

class TestIncrementalUpdate:
    async def test_update_subset_statuses(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Passing part of the old list with updated statuses should merge incrementally."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "pending"},
            {"title": "Task B", "status": "in_progress"},
            {"title": "Task C", "status": "pending"},
        ])

        result = await tool(_make_params([
            Todo(title="Task A", status="done"),
            Todo(title="Task B", status="done"),
        ]))

        assert result.is_error is False
        assert "updated" in result.output.lower()

        state = _read_state(tmp_subagent_state)
        saved = {t["title"]: t["status"] for t in state.get("todos", [])}
        assert saved == {
            "Task A": "done",
            "Task B": "done",
            "Task C": "pending",
        }

    async def test_update_single_todo(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Passing a single Todo object that exists in old list updates just that item."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "pending"},
            {"title": "Task B", "status": "pending"},
        ])

        result = await tool(_make_params(Todo(title="Task A", status="in_progress")))

        assert result.is_error is False
        state = _read_state(tmp_subagent_state)
        saved = {t["title"]: t["status"] for t in state.get("todos", [])}
        assert saved == {"Task A": "in_progress", "Task B": "pending"}

    async def test_no_change_when_same_status(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Passing identical statuses preserves state and returns success."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "done"},
            {"title": "Task B", "status": "in_progress"},
        ])

        result = await tool(_make_params([Todo(title="Task A", status="done")]))

        assert result.is_error is False
        state = _read_state(tmp_subagent_state)
        saved = {t["title"]: t["status"] for t in state.get("todos", [])}
        assert saved == {"Task A": "done", "Task B": "in_progress"}


# ---------------------------------------------------------------------------
# 2. Error when new content differs while old has unfinished items
# ---------------------------------------------------------------------------

class TestErrorOnDifferentContent:
    async def test_new_titles_while_old_unfinished(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Adding new titles while old todos are not all done returns an error naming unfinished items."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "pending"},
            {"title": "Task B", "status": "in_progress"},
            {"title": "Task C", "status": "done"},
        ])

        result = await tool(_make_params([
            Todo(title="Task A", status="done"),
            Todo(title="New Task", status="pending"),
        ]))

        assert result.is_error is True
        assert "Cannot replace with new todos while old todos are not all done" in result.output
        assert "Unfinished: Task A, Task B" in result.output

    async def test_clear_while_old_unfinished(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Clearing todos while old todos are not all done returns an error naming unfinished items."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "pending"},
            {"title": "Task B", "status": "done"},
        ])

        result = await tool(_make_params([]))

        assert result.is_error is True
        assert "Cannot clear todos while old todos are not all done" in result.output
        assert "Unfinished: Task A" in result.output

    async def test_error_precision_for_multiple_unfinished(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Error message precisely lists all unfinished items, comma-separated."""
        _write_state(tmp_subagent_state, [
            {"title": "Alpha", "status": "pending"},
            {"title": "Beta", "status": "in_progress"},
            {"title": "Gamma", "status": "pending"},
            {"title": "Delta", "status": "done"},
        ])

        result = await tool(_make_params([Todo(title="Omega", status="pending")]))

        assert result.is_error is True
        assert "Unfinished: Alpha, Beta, Gamma" in result.output


# ---------------------------------------------------------------------------
# 3. Ensure current functionality works
# ---------------------------------------------------------------------------

class TestCurrentFunctionality:
    # ---- Read mode ---------------------------------------------------------

    async def test_read_empty_list(self, tool: SetTodoList) -> None:
        """Reading with no persisted state returns 'empty' message."""
        result = await tool(_make_params(None))
        assert result.is_error is False
        assert "empty" in result.output.lower()

    async def test_read_existing_list(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Reading returns formatted todo list."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "in_progress"},
            {"title": "Task B", "status": "done"},
        ])

        result = await tool(_make_params(None))
        assert result.is_error is False
        assert "Current todo list:" in result.output
        assert "[in_progress] Task A" in result.output
        assert "[done] Task B" in result.output

    # ---- Force replace -----------------------------------------------------

    async def test_force_replace_bypasses_validation(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """force_replace=True allows adding new titles even when old items are unfinished."""
        _write_state(tmp_subagent_state, [
            {"title": "Old Task", "status": "pending"},
        ])

        result = await tool(_make_params(
            [Todo(title="Brand New Task", status="pending")],
            force_replace=True,
        ))

        assert result.is_error is False
        assert "force_replace=True" in result.output
        state = _read_state(tmp_subagent_state)
        titles = [t["title"] for t in state.get("todos", [])]
        assert titles == ["Brand New Task"]

    # ---- Duplicate titles --------------------------------------------------

    async def test_duplicate_titles_error(self, tool: SetTodoList) -> None:
        """Duplicate titles in the new list produce an error."""
        result = await tool(_make_params([
            Todo(title="Dup", status="pending"),
            Todo(title="Dup", status="done"),
        ]))

        assert result.is_error is True
        assert "Duplicate todo titles found: Dup" in result.output

    # ---- Max limit ---------------------------------------------------------

    async def test_exceed_max_limit(self, tool: SetTodoList) -> None:
        """More than 4096 items produce an error."""
        huge_list = [Todo(title=f"Task {i}", status="pending") for i in range(4097)]
        result = await tool(_make_params(huge_list))

        assert result.is_error is True
        assert "exceeds maximum limit" in result.output

    # ---- Regression: done -> not-done --------------------------------------

    async def test_regression_done_to_pending(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Changing a done item back to pending is treated as regression: error and reverted."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "done"},
            {"title": "Task B", "status": "in_progress"},
        ])

        result = await tool(_make_params([
            Todo(title="Task A", status="pending"),
            Todo(title="Task B", status="done"),
        ]))

        assert result.is_error is True
        assert "Cannot regress completed todos" in result.output
        assert "Task A" in result.output

        state = _read_state(tmp_subagent_state)
        saved = {t["title"]: t["status"] for t in state.get("todos", [])}
        # Regression is reverted before saving
        assert saved["Task A"] == "done"
        assert saved["Task B"] == "done"

    async def test_regression_done_to_in_progress(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Changing a done item back to in_progress is also treated as regression."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "done"},
        ])

        result = await tool(_make_params([Todo(title="Task A", status="in_progress")]))

        assert result.is_error is True
        assert "Cannot regress completed todos" in result.output
        state = _read_state(tmp_subagent_state)
        assert state["todos"][0]["status"] == "done"

    # ---- Clear when all done -----------------------------------------------

    async def test_clear_when_all_done(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Clearing todos is allowed when all old todos are done."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "done"},
            {"title": "Task B", "status": "done"},
        ])

        result = await tool(_make_params([]))

        assert result.is_error is False
        state = _read_state(tmp_subagent_state)
        assert state.get("todos") == []

    # ---- Replace when all old done -----------------------------------------

    async def test_replace_when_all_old_done(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """When all old todos are done, new titles replace the list entirely."""
        _write_state(tmp_subagent_state, [
            {"title": "Old A", "status": "done"},
            {"title": "Old B", "status": "done"},
        ])

        result = await tool(_make_params([
            Todo(title="New A", status="pending"),
            Todo(title="New B", status="in_progress"),
        ]))

        assert result.is_error is False
        state = _read_state(tmp_subagent_state)
        titles = [t["title"] for t in state.get("todos", [])]
        assert titles == ["New A", "New B"]

    # ---- Display block present on success ----------------------------------

    async def test_display_block_on_success(self, tool: SetTodoList, tmp_subagent_state: Path) -> None:
        """Successful writes include a TodoDisplayBlock in the display list."""
        _write_state(tmp_subagent_state, [
            {"title": "Task A", "status": "pending"},
        ])

        result = await tool(_make_params([Todo(title="Task A", status="done")]))

        assert result.is_error is False
        assert any(isinstance(d, TodoDisplayBlock) for d in result.display)
