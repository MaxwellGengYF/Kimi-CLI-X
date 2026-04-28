"""Thread pool execution engine for DAGs."""
from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from kimix.dag.dag import Context, DAG, TaskNode
from kimix.dag.utils import CycleError, DependencyError, ExecutionError


class TopologicalSorter:
    """Topological sort for dependency resolution using Kahn's algorithm."""

    def __init__(self, edges: dict[str, set[str]]) -> None:
        self.edges = {k: set(v) for k, v in edges.items()}

    def sort(self) -> list[str]:
        """Return a topologically sorted list of node names.

        Raises:
            CycleError: If the graph contains a cycle.
        """
        in_degree: dict[str, int] = {}
        dependents: dict[str, set[str]] = {}

        for node, deps in self.edges.items():
            in_degree[node] = len(deps)
            dependents.setdefault(node, set())
            for dep in deps:
                dependents.setdefault(dep, set()).add(node)

        for deps in self.edges.values():
            for dep in deps:
                in_degree.setdefault(dep, 0)
                dependents.setdefault(dep, set())

        queue = [n for n, d in in_degree.items() if d == 0]
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for dependent in dependents.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(in_degree):
            raise CycleError("Cycle detected in dependency graph")

        return result


class Executor:
    """Thread pool executor that respects DAG dependencies."""

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers

    def execute(self, dag: DAG, ctx: Context | None = None) -> dict[str, Any]:
        """Execute all tasks in the DAG respecting dependencies.

        Tasks with satisfied dependencies are submitted to a thread pool.
        If a task fails, dependent tasks receive DependencyError.

        Args:
            dag: The DAG to execute.
            ctx: Optional shared context. Created if not provided.

        Returns:
            Mapping from node name to result.

        Raises:
            ExecutionError: If any task fails.
        """
        ctx = ctx or Context()
        dag.validate()

        results: dict[str, Any] = {}
        errors: dict[str, Exception] = {}
        submitted: set[str] = set()
        finished_count = 0
        lock = threading.Lock()
        all_done = threading.Event()

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:

            def _submit_ready() -> None:
                nonlocal finished_count
                done_nodes = set(results) | set(errors)
                for name, node in dag.nodes.items():
                    if name in submitted:
                        continue
                    if not node.dependencies.issubset(done_nodes):
                        continue

                    submitted.add(name)

                    failed_deps = [d for d in node.dependencies if d in errors]
                    if failed_deps:
                        err = DependencyError(
                            f"Task {name!r} aborted because dependencies failed: {failed_deps}"
                        )
                        with lock:
                            errors[name] = err
                            finished_count += 1
                            node.mark_done(error=err)
                            if finished_count >= len(dag):
                                all_done.set()
                        continue

                    future = pool.submit(_run_node, node, ctx)
                    future.add_done_callback(lambda f, n=name: _on_done(f, n))

            def _run_node(node: TaskNode, ctx: Context) -> Any:
                ctx.check_cancelled()
                return node.execute(ctx)

            def _on_done(future: Future, name: str) -> None:
                nonlocal finished_count
                node = dag.get_node(name)
                try:
                    result = future.result()
                    with lock:
                        results[name] = result
                        node.mark_done(result=result)
                except Exception as e:
                    with lock:
                        errors[name] = e
                        node.mark_done(error=e)

                with lock:
                    finished_count += 1
                    if finished_count >= len(dag):
                        all_done.set()
                        return

                if not ctx.cancelled:
                    _submit_ready()

            _submit_ready()
            if finished_count >= len(dag):
                all_done.set()
            all_done.wait()

        if errors:
            raise ExecutionError(
                f"{len(errors)} task(s) failed: {list(errors.keys())}",
                errors=errors,
            )

        return results
