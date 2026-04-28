"""DAG utility functions for validation and cycle detection."""
from __future__ import annotations

from typing import Any


class DAGValidationError(ValueError):
    """Raised when a DAG fails structural validation."""


class CycleError(DAGValidationError):
    """Raised when a cycle is detected in the DAG."""


class DependencyError(RuntimeError):
    """Raised when a task's dependency fails."""


class ExecutionError(RuntimeError):
    """Raised when one or more tasks fail during execution."""

    def __init__(
        self,
        message: str,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = errors or {}


def detect_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """Detect a cycle in a directed graph using DFS.

    Args:
        graph: Mapping from node name to its dependency names.

    Returns:
        A cycle path if found, otherwise None.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    state: dict[str, int] = {node: WHITE for node in graph}
    for deps in graph.values():
        for dep in deps:
            if dep not in state:
                state[dep] = WHITE

    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        state[node] = GRAY
        path.append(node)
        for dep in graph.get(node, set()):
            if state.get(dep, WHITE) == GRAY:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if state.get(dep, WHITE) == WHITE:
                result = dfs(dep)
                if result:
                    return result
        path.pop()
        state[node] = BLACK
        return None

    for node in list(state.keys()):
        if state[node] == WHITE:
            cycle = dfs(node)
            if cycle:
                return cycle
    return None


def validate_dag(nodes: dict[str, Any], edges: dict[str, set[str]]) -> None:
    """Validate a DAG structure.

    Args:
        nodes: Mapping of node names to node objects.
        edges: Mapping of node names to their dependency names.

    Raises:
        DAGValidationError: If nodes or edges are invalid.
        CycleError: If a cycle is detected.
    """
    for node, deps in edges.items():
        if node not in nodes:
            raise DAGValidationError(f"Edge references unknown node: {node!r}")
        for dep in deps:
            if dep not in nodes:
                raise DAGValidationError(
                    f"Node {node!r} depends on unknown node {dep!r}"
                )

    for node, deps in edges.items():
        if node in deps:
            raise CycleError(f"Self-reference detected on node {node!r}")

    cycle = detect_cycle(edges)
    if cycle:
        raise CycleError(f"Cycle detected: {' -> '.join(cycle)}")
