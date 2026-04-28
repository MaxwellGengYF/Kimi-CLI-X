"""Core DAG and TaskNode definitions."""
from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Any, Callable

from kimix.dag.utils import (
    DAGValidationError,
    validate_dag,
)


class Context:
    """Shared execution context with cancellation support."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cancelled = threading.Event()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Signal cancellation to all tasks."""
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._cancelled.is_set()

    def check_cancelled(self) -> None:
        """Raise RuntimeError if cancellation has been requested."""
        if self.cancelled:
            raise RuntimeError("Execution cancelled")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from shared state."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in shared state."""
        with self._lock:
            self._data[key] = value

    def update(self, other: dict[str, Any]) -> None:
        """Update shared state with a mapping."""
        with self._lock:
            self._data.update(other)


class TaskNode:
    """A node in the DAG representing a unit of work."""

    def __init__(
        self,
        name: str,
        func: Callable[..., Any] | Any,
        params: Any | None = None,
        dependencies: set[str] | list[str] | None = None,
        retries: int = 0,
    ) -> None:
        self.name = name
        self.func = func
        self.params = params
        self.dependencies = set(dependencies) if dependencies else set()
        self.retries = max(0, retries)
        self.result: Any = None
        self.error: Exception | None = None
        self._done = threading.Event()
        self._lock = threading.Lock()

    @property
    def done(self) -> bool:
        """Whether this node has finished execution."""
        return self._done.is_set()

    def execute(self, ctx: Context) -> Any:
        """Execute this node's callable with retry logic.

        Args:
            ctx: Shared execution context.

        Returns:
            The return value of the callable.

        Raises:
            RuntimeError: If context is cancelled.
            Exception: The last exception after all retries are exhausted.
        """
        ctx.check_cancelled()

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                if inspect.iscoroutinefunction(self.func):
                    result = asyncio.run(self.func(ctx))
                else:
                    result = self.func(ctx)
                return result
            except Exception as e:
                last_error = e
                if attempt < self.retries:
                    continue
                raise last_error
        raise last_error if last_error else RuntimeError("Execution failed")

    def mark_done(self, result: Any = None, error: Exception | None = None) -> None:
        """Mark the node as completed with an optional result or error."""
        with self._lock:
            self.result = result
            self.error = error
            self._done.set()

    def __repr__(self) -> str:
        return f"TaskNode(name={self.name!r}, deps={self.dependencies})"


class DAG:
    """Directed Acyclic Graph for task dependency management."""

    def __init__(self) -> None:
        self._nodes: dict[str, TaskNode] = {}
        self._edges: dict[str, set[str]] = {}

    @property
    def nodes(self) -> dict[str, TaskNode]:
        """Read-only access to nodes."""
        return dict(self._nodes)

    @property
    def edges(self) -> dict[str, set[str]]:
        """Read-only access to edges (node -> dependencies)."""
        return {k: set(v) for k, v in self._edges.items()}

    def add_node(self, node: TaskNode) -> None:
        """Add a task node to the DAG.

        Raises:
            DAGValidationError: If a node with the same name already exists.
        """
        if node.name in self._nodes:
            raise DAGValidationError(f"Node {node.name!r} already exists")
        self._nodes[node.name] = node
        self._edges[node.name] = set(node.dependencies)

    def add_edge(self, upstream: str, downstream: str) -> None:
        """Add a dependency edge: upstream must complete before downstream.

        Raises:
            KeyError: If either node does not exist.
        """
        if upstream not in self._nodes:
            raise KeyError(f"Upstream node {upstream!r} not found")
        if downstream not in self._nodes:
            raise KeyError(f"Downstream node {downstream!r} not found")
        self._edges[downstream].add(upstream)
        self._nodes[downstream].dependencies.add(upstream)

    def get_node(self, name: str) -> TaskNode:
        """Retrieve a node by name.

        Raises:
            KeyError: If the node does not exist.
        """
        if name not in self._nodes:
            raise KeyError(f"Node {name!r} not found")
        return self._nodes[name]

    def validate(self) -> None:
        """Validate the DAG structure.

        Raises:
            CycleError: If a cycle is detected.
            DAGValidationError: If the structure is invalid.
        """
        validate_dag(self._nodes, self._edges)

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def __repr__(self) -> str:
        return f"DAG(nodes={list(self._nodes)}, edges={dict(self._edges)})"
