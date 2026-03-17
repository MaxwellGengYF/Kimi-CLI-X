from pathlib import Path
from typing import Literal, override

from kosong.tooling import CallableTool2, ToolReturnValue, ToolError
from pydantic import BaseModel, Field

from kimi_cli.tools.display import TodoDisplayBlock, TodoDisplayItem
from kimi_cli.tools.utils import load_desc

import threading
_curr_todo_items = threading.local()


DEFAULT_DB_PATH = Path.home() / ".kimi/sessions/todo.db"


def set_current_id(id):
    _curr_todo_items.id = id


class Todo(BaseModel):
    title: str = Field(description="The title of the todo", min_length=1)
    status: Literal["pending", "in_progress", "done"] = Field(
        description="The status of the todo")


class Params(BaseModel):
    todos: list[Todo] = Field(description="The updated todo list")


def _ser_params(p: Params) -> str:
    return p.model_dump_json()


def _deser_params(s: str) -> Params:
    return Params.model_validate_json(s)


def get_todo_list(id):
    import dbm
    try:
        with dbm.open(DEFAULT_DB_PATH, 'c') as db:
            key = str(id).encode('utf-8')
            if key in db:
                return _deser_params(db[key].decode('utf-8'))
    except Exception:
        pass
    return None


_todo_called = False


class SetTodoList(CallableTool2[Params]):
    name: str = "SetTodoList"
    description: str = load_desc(Path(__file__).parent / "set_todo_list.md")
    params: type[Params] = Params

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        global _todo_called
        items = [TodoDisplayItem(title=todo.title, status=todo.status)
                 for todo in params.todos]
        id = getattr(_curr_todo_items, 'id', None)
        if id is not None:
            import dbm
            try:
                with dbm.open(DEFAULT_DB_PATH, 'c') as db:
                    db[str(id).encode('utf-8')
                       ] = _ser_params(params).encode('utf-8')
            except Exception as exc:
                return ToolError(
                    output="",
                    message=str(exc),
                    brief="Set success, but failed to save todo to database",
                )
        _todo_called = True
        return ToolReturnValue(
            is_error=False,
            output="",
            message="Todo list updated",
            display=[TodoDisplayBlock(items=items)],
        )


class GetParams(BaseModel):
    pass


class GetTodoList(CallableTool2[GetParams]):
    name: str = "GetTodoList"
    description: str = load_desc(Path(__file__).parent / "get_todo_list.md")
    params: type[GetParams] = GetParams

    @override
    async def __call__(self, params: GetParams) -> ToolReturnValue:
        id = getattr(_curr_todo_items, 'id', None)
        if id is None:
            return ToolError(
                output="",
                message="No todo list session found"
            )

        stored = get_todo_list(id)
        if stored is None:
            return ToolError(
                output="",
                message="No todo list found"
            )
        return ToolReturnValue(
            is_error=False,
            output=stored,
            message="Todo list retrieved",
        )
