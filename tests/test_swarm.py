"""Comprehensive tests for swarm DAG planning tools."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from kimi_cli.session import Session
from kimix.dag import DAG, TaskNode
from kimix.dag.utils import DAGValidationError

from my_tools.swarm import AddNode, AddEdge, AddNodeParams, AddEdgeParams


@pytest.fixture
def mock_session() -> Session:
    """Create a session with empty custom_data."""
    session = MagicMock(spec=Session)
    session.custom_data = {}
    return session


@pytest.fixture
def add_node_tool(mock_session: Session) -> AddNode:
    return AddNode(mock_session)


@pytest.fixture
def add_edge_tool(mock_session: Session) -> AddEdge:
    return AddEdge(mock_session)


class TestAddNode:
    def test_init(self, add_node_tool: AddNode) -> None:
        assert add_node_tool.name == "AddNode"
        assert add_node_tool.description
        assert add_node_tool.params is AddNodeParams

    @pytest.mark.asyncio
    async def test_add_first_node_creates_dag(self, mock_session: Session, add_node_tool: AddNode) -> None:
        params = AddNodeParams(prompt="Implement feature A")
        result = await add_node_tool(params)
        assert not result.is_error
        assert "node_0" in result.output
        assert "swarm_dag" in mock_session.custom_data
        dag = mock_session.custom_data["swarm_dag"]
        assert isinstance(dag, DAG)
        assert len(dag) == 1
        assert "node_0" in dag

    @pytest.mark.asyncio
    async def test_add_multiple_nodes_increments_ids(self, mock_session: Session, add_node_tool: AddNode) -> None:
        for i in range(3):
            params = AddNodeParams(prompt=f"Task {i}")
            result = await add_node_tool(params)
            assert not result.is_error
            assert result.output == f"node_{i}"

        dag = mock_session.custom_data["swarm_dag"]
        assert len(dag) == 3
        assert "node_0" in dag
        assert "node_1" in dag
        assert "node_2" in dag

    @pytest.mark.asyncio
    async def test_node_stores_prompt(self, mock_session: Session, add_node_tool: AddNode) -> None:
        prompt = "Write tests for module X"
        params = AddNodeParams(prompt=prompt)
        result = await add_node_tool(params)
        assert not result.is_error

        dag = mock_session.custom_data["swarm_dag"]
        node = dag.get_node(result.output)
        assert isinstance(node, TaskNode)
        # TaskNode.func returns the prompt when executed
        assert node.func is not None

    @pytest.mark.asyncio
    async def test_node_execution_returns_prompt(self, mock_session: Session, add_node_tool: AddNode) -> None:
        from unittest import mock
        prompt = "Refactor codebase"
        params = AddNodeParams(prompt=prompt)
        result = await add_node_tool(params)
        assert not result.is_error

        dag = mock_session.custom_data["swarm_dag"]
        node = dag.get_node(result.output)
        from kimix.dag import Context
        ctx = Context()
        with mock.patch("kimix.dag.agent_swarm.execute_swarm", new=mock.AsyncMock(return_value=prompt)):
            execution_result = node.execute(ctx)
        assert execution_result == prompt

    @pytest.mark.asyncio
    async def test_counter_persists(self, mock_session: Session, add_node_tool: AddNode) -> None:
        mock_session.custom_data["swarm_node_counter"] = 5
        params = AddNodeParams(prompt="Task after counter 5")
        result = await add_node_tool(params)
        assert not result.is_error
        assert result.output == "node_5"
        assert mock_session.custom_data["swarm_node_counter"] == 6


class TestAddEdge:
    def test_init(self, add_edge_tool: AddEdge) -> None:
        assert add_edge_tool.name == "AddEdge"
        assert add_edge_tool.description
        assert add_edge_tool.params is AddEdgeParams

    @pytest.mark.asyncio
    async def test_add_edge_success(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        # Create two nodes
        r1 = await add_node_tool(AddNodeParams(prompt="Task 1"))
        r2 = await add_node_tool(AddNodeParams(prompt="Task 2"))
        upstream = r1.output
        downstream = r2.output

        params = AddEdgeParams(upstream=upstream, downstream=downstream)
        result = await add_edge_tool(params)
        assert not result.is_error
        assert upstream in result.output
        assert downstream in result.output

        dag = mock_session.custom_data["swarm_dag"]
        assert dag.edges[downstream] == {upstream}
        assert dag.get_node(downstream).dependencies == {upstream}

    @pytest.mark.asyncio
    async def test_add_edge_without_dag_returns_error(self, mock_session: Session, add_edge_tool: AddEdge) -> None:
        params = AddEdgeParams(upstream="node_0", downstream="node_1")
        result = await add_edge_tool(params)
        assert result.is_error
        assert "not found" in result.message.lower() or "initialized" in result.message.lower()

    @pytest.mark.asyncio
    async def test_add_edge_missing_upstream(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        await add_node_tool(AddNodeParams(prompt="Task 1"))
        params = AddEdgeParams(upstream="missing", downstream="node_0")
        result = await add_edge_tool(params)
        assert result.is_error
        assert "Upstream" in result.message or "not found" in result.message

    @pytest.mark.asyncio
    async def test_add_edge_missing_downstream(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        await add_node_tool(AddNodeParams(prompt="Task 1"))
        params = AddEdgeParams(upstream="node_0", downstream="missing")
        result = await add_edge_tool(params)
        assert result.is_error
        assert "Downstream" in result.message or "not found" in result.message

    @pytest.mark.asyncio
    async def test_add_edge_creates_cycle(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        # node_0 -> node_1
        await add_node_tool(AddNodeParams(prompt="Task 0"))
        await add_node_tool(AddNodeParams(prompt="Task 1"))
        await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_1"))

        # node_1 -> node_0 should create a cycle
        params = AddEdgeParams(upstream="node_1", downstream="node_0")
        result = await add_edge_tool(params)
        assert result.is_error
        assert "Cycle" in result.message or "cycle" in result.message.lower()

    @pytest.mark.asyncio
    async def test_add_edge_self_reference(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        await add_node_tool(AddNodeParams(prompt="Task 0"))
        params = AddEdgeParams(upstream="node_0", downstream="node_0")
        result = await add_edge_tool(params)
        assert result.is_error
        assert "Cycle" in result.message or "Self-reference" in result.message

    @pytest.mark.asyncio
    async def test_add_edge_diamond_structure(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        # Create diamond: 0 -> 1, 0 -> 2, 1 -> 3, 2 -> 3
        for i in range(4):
            await add_node_tool(AddNodeParams(prompt=f"Task {i}"))

        await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_1"))
        await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_2"))
        await add_edge_tool(AddEdgeParams(upstream="node_1", downstream="node_3"))
        await add_edge_tool(AddEdgeParams(upstream="node_2", downstream="node_3"))

        dag = mock_session.custom_data["swarm_dag"]
        assert dag.get_node("node_1").dependencies == {"node_0"}
        assert dag.get_node("node_2").dependencies == {"node_0"}
        assert dag.get_node("node_3").dependencies == {"node_1", "node_2"}
        dag.validate()  # should not raise

    @pytest.mark.asyncio
    async def test_add_edge_multiple_independent_edges(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        for i in range(4):
            await add_node_tool(AddNodeParams(prompt=f"Task {i}"))

        r1 = await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_1"))
        r2 = await add_edge_tool(AddEdgeParams(upstream="node_2", downstream="node_3"))
        assert not r1.is_error
        assert not r2.is_error

        dag = mock_session.custom_data["swarm_dag"]
        assert dag.edges["node_1"] == {"node_0"}
        assert dag.edges["node_3"] == {"node_2"}

    @pytest.mark.asyncio
    async def test_add_edge_chain(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        for i in range(3):
            await add_node_tool(AddNodeParams(prompt=f"Task {i}"))

        await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_1"))
        await add_edge_tool(AddEdgeParams(upstream="node_1", downstream="node_2"))

        dag = mock_session.custom_data["swarm_dag"]
        assert dag.get_node("node_2").dependencies == {"node_1"}

    @pytest.mark.asyncio
    async def test_add_edge_duplicate_is_idempotent(self, mock_session: Session, add_node_tool: AddNode, add_edge_tool: AddEdge) -> None:
        await add_node_tool(AddNodeParams(prompt="Task 0"))
        await add_node_tool(AddNodeParams(prompt="Task 1"))

        r1 = await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_1"))
        r2 = await add_edge_tool(AddEdgeParams(upstream="node_0", downstream="node_1"))
        assert not r1.is_error
        assert not r2.is_error

        dag = mock_session.custom_data["swarm_dag"]
        assert dag.edges["node_1"] == {"node_0"}


class TestSwarmDAGIntegration:
    @pytest.mark.asyncio
    async def test_full_planning_workflow(self, mock_session: Session) -> None:
        """Simulate a leader agent planning a multi-step coding task."""
        add_node = AddNode(mock_session)
        add_edge = AddEdge(mock_session)

        # Plan: read -> design -> implement -> test
        read = await add_node(AddNodeParams(prompt="Read and analyze existing code"))
        design = await add_node(AddNodeParams(prompt="Design the solution"))
        implement = await add_node(AddNodeParams(prompt="Implement the feature"))
        test = await add_node(AddNodeParams(prompt="Write and run tests"))

        assert not read.is_error
        assert not design.is_error
        assert not implement.is_error
        assert not test.is_error

        await add_edge(AddEdgeParams(upstream=read.output, downstream=design.output))
        await add_edge(AddEdgeParams(upstream=design.output, downstream=implement.output))
        await add_edge(AddEdgeParams(upstream=implement.output, downstream=test.output))

        dag = mock_session.custom_data["swarm_dag"]
        assert len(dag) == 4
        dag.validate()

        # Check topological order
        from kimix.dag.executor import TopologicalSorter
        ts = TopologicalSorter(dag.edges)
        order = ts.sort()
        assert order.index(read.output) < order.index(design.output)
        assert order.index(design.output) < order.index(implement.output)
        assert order.index(implement.output) < order.index(test.output)

    @pytest.mark.asyncio
    async def test_parallel_tasks(self, mock_session: Session) -> None:
        """Plan parallel independent sub-tasks."""
        add_node = AddNode(mock_session)
        add_edge = AddEdge(mock_session)

        setup = await add_node(AddNodeParams(prompt="Setup environment"))
        frontend = await add_node(AddNodeParams(prompt="Implement frontend"))
        backend = await add_node(AddNodeParams(prompt="Implement backend"))
        integrate = await add_node(AddNodeParams(prompt="Integrate frontend and backend"))

        await add_edge(AddEdgeParams(upstream=setup.output, downstream=frontend.output))
        await add_edge(AddEdgeParams(upstream=setup.output, downstream=backend.output))
        await add_edge(AddEdgeParams(upstream=frontend.output, downstream=integrate.output))
        await add_edge(AddEdgeParams(upstream=backend.output, downstream=integrate.output))

        dag = mock_session.custom_data["swarm_dag"]
        dag.validate()

    @pytest.mark.asyncio
    async def test_error_recovery_planning(self, mock_session: Session) -> None:
        """Ensure errors are returned properly without raising."""
        add_edge = AddEdge(mock_session)
        result = await add_edge(AddEdgeParams(upstream="nonexistent", downstream="also_missing"))
        assert result.is_error
        assert isinstance(result.output, str)

    def test_tool_classes_in_all(self) -> None:
        from my_tools import swarm
        assert hasattr(swarm, "AddNode")
        assert hasattr(swarm, "AddEdge")
        assert hasattr(swarm, "AddNodeParams")
        assert hasattr(swarm, "AddEdgeParams")
