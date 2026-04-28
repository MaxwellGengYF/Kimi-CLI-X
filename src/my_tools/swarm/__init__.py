"""Swarm DAG planning tools for leader coding-agent."""
from __future__ import annotations

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from typing import Any
import tempfile
from pathlib import Path

from kimi_cli.session import Session
from kimix.dag import DAG, TaskNode
from kimix.dag.utils import DAGValidationError


class AddNodeParams(BaseModel):
    """Parameters for AddNode tool."""
    prompt: str = Field(
        description="Task instructions for the sub-agent."
    )


class AddNode(CallableTool2[AddNodeParams]):
    """Add a sub-agent task node to the swarm DAG."""
    name: str = "AddNode"
    description: str = (
        "Add a sub-agent task node to the swarm DAG. "
        "Returns the unique node ID that can be used with AddEdge."
    )
    params: type[AddNodeParams] = AddNodeParams

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def __call__(self, params: AddNodeParams) -> ToolReturnValue:
        try:
            dag: DAG = self._session.custom_data.setdefault("swarm_dag", DAG())
            counter: int = self._session.custom_data.setdefault("swarm_node_counter", 0)
            node_id = f"node_{counter}"
            self._session.custom_data["swarm_node_counter"] = counter + 1

            async def _task(ctx: Any) -> str:
                temp_dir = Path(tempfile.mkdtemp(prefix=f"swarm_{node_id}_"))
                from kimix.dag.agent_swarm import execute_swarm, _ALL_VFS_PATH
                result: str
                try:
                    result = await execute_swarm(node_id, params.prompt, temp_dir)
                except Exception as exc:
                    result = f"Error: {exc}"
                return result

            node = TaskNode(node_id, _task)
            dag.add_node(node)
            return ToolOk(output=node_id, message=f"Node '{node_id}' added to swarm DAG.")
        except Exception as exc:
            return ToolError(
                message=str(exc),
                output="",
                brief="Failed to add node"
            )


class AddEdgeParams(BaseModel):
    """Parameters for AddEdge tool."""
    upstream: str = Field(
        description="Upstream node ID (must complete first)."
    )
    downstream: str = Field(
        description="Downstream node ID (depends on upstream)."
    )


class AddEdge(CallableTool2[AddEdgeParams]):
    """Add a dependency edge between two nodes in the swarm DAG."""
    name: str = "AddEdge"
    description: str = (
        "Add a dependency edge: upstream task must complete before downstream task. "
        "Both node IDs must exist in the swarm DAG."
    )
    params: type[AddEdgeParams] = AddEdgeParams

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def __call__(self, params: AddEdgeParams) -> ToolReturnValue:
        try:
            dag: DAG | None = self._session.custom_data.get("swarm_dag")
            if dag is None:
                return ToolError(
                    message="Swarm DAG not found. Use AddNode first.",
                    output="",
                    brief="DAG not initialized"
                )
            dag.add_edge(params.upstream, params.downstream)
            return ToolOk(
                output=f"Edge added: '{params.upstream}' -> '{params.downstream}'",
                message=f"Upstream '{params.upstream}' must complete before downstream '{params.downstream}'."
            )
        except (KeyError, DAGValidationError) as exc:
            return ToolError(
                message=str(exc),
                output="",
                brief="Edge validation failed"
            )
        except Exception as exc:
            return ToolError(
                message=str(exc),
                output="",
                brief="Failed to add edge"
            )


__all__ = [
    "AddNode",
    "AddNodeParams",
    "AddEdge",
    "AddEdgeParams",
]
