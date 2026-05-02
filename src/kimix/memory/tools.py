"""Memory system tool interface using CallableTool2 pattern."""

from typing import Any

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from kimix.memory.system import AgentMemorySystem
from kimix.memory.types import MemoryType


# Global memory system instance (initialized lazily)
_memory_system: AgentMemorySystem | None = None


def _get_memory_system() -> AgentMemorySystem:
    """Get or initialize the global memory system instance."""
    global _memory_system
    if _memory_system is None:
        _memory_system = AgentMemorySystem()
    return _memory_system


class RememberParams(BaseModel):
    """Parameters for remembering a fact or observation."""
    content: str = Field(description="The fact, knowledge, or observation to remember.")
    importance: float = Field(default=5.0, ge=0.0, le=10.0, description="Importance score (0-10).")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization.")
    memory_type: str = Field(default="semantic", description="Memory type: episodic, semantic, procedural, working.")
    long_term: bool = Field(default=True, description="Memory tier to store in: False for 'short_term'.")


class Remember(CallableTool2):
    """Store a fact, observation, or knowledge in memory (short-term or long-term)."""
    name: str = "Remember"
    description: str = "Store a fact, observation, or knowledge in the agent's memory (short-term or long-term)."
    params: type[BaseModel] = RememberParams

    async def __call__(self, params: RememberParams) -> ToolReturnValue:
        try:
            memory = _get_memory_system()
            if params.long_term:
                entry = memory.perceive(
                    observation=params.content,
                    importance=params.importance,
                    tags=params.tags
                )
                return ToolOk(output=f"Perceived: {entry.content[:100]}... (importance: {entry.importance})")
            else:
                mt = MemoryType(params.memory_type) if params.memory_type else MemoryType.SEMANTIC
                entry = memory.remember(
                    fact=params.content,
                    importance=params.importance,
                    tags=params.tags,
                    memory_type=mt,
                )
                return ToolOk(output=f"Remembered: {entry.content[:100]}... (importance: {entry.importance})")
        except Exception as e:
            return ToolError(message=str(e), output="", brief="Failed to store memory")


class RecallParams(BaseModel):
    """Parameters for recalling memories."""
    query: str = Field(description="Query string to search memories.")
    context_size: int = Field(default=5, ge=1, le=20, description="Number of results per tier.")
    use_working: bool = Field(default=True, description="Include working memory.")
    use_short: bool = Field(default=True, description="Include short-term memory.")
    use_long: bool = Field(default=True, description="Include long-term memory.")
    tags: list[str] = Field(default_factory=list, description="Filter by tags for long-term memory.")


class Recall(CallableTool2):
    """Recall memories from all memory tiers."""
    name: str = "Recall"
    description: str = "Retrieve relevant memories from working, short-term, and long-term memory tiers."
    params: type[BaseModel] = RecallParams

    async def __call__(self, params: RecallParams) -> ToolReturnValue:
        try:
            memory = _get_memory_system()
            results = memory.recall(
                query=params.query,
                context_size=params.context_size,
                use_working=params.use_working,
                use_short=params.use_short,
                use_long=params.use_long,
                tag_filter=params.tags if params.tags else None,
            )
            output_parts: list[str] = []
            for tier, entries in results.items():
                if entries:
                    output_parts.append(f"\n=== {tier.upper()} ===")
                    for e in entries:
                        output_parts.append(f"- [{e.memory_type.value}] {e.content}")
            output = "\n".join(output_parts) if output_parts else "No memories found."
            return ToolOk(output=output)
        except Exception as e:
            return ToolError(message=str(e), output="", brief="Failed to recall memories")


class GetContextParams(BaseModel):
    """Parameters for getting LLM context."""
    query: str = Field(description="Query to generate context for.")
    max_tokens: int = Field(default=2000, ge=100, le=8000, description="Maximum characters for context.")


class GetContext(CallableTool2):
    """Generate RAG-style context prompt for LLM."""
    name: str = "GetContext"
    description: str = "Generate a context prompt from all memory tiers for LLM consumption."
    params: type[BaseModel] = GetContextParams

    async def __call__(self, params: GetContextParams) -> ToolReturnValue:
        try:
            memory = _get_memory_system()
            context = memory.get_context_for_llm(params.query, max_tokens=params.max_tokens)
            return ToolOk(output=context)
        except Exception as e:
            return ToolError(message=str(e), output="", brief="Failed to generate context")


class ReflectParams(BaseModel):
    """Parameters for memory system reflection."""


class Reflect(CallableTool2):
    """Get memory system status report."""
    name: str = "Reflect"
    description: str = "Get a status report of the memory system (working, short-term, long-term)."
    params: type[BaseModel] = ReflectParams

    async def __call__(self, params: ReflectParams) -> ToolReturnValue:
        try:
            memory = _get_memory_system()
            report = memory.reflect()
            return ToolOk(output=report)
        except Exception as e:
            return ToolError(message=str(e), output="", brief="Failed to reflect on memory")
