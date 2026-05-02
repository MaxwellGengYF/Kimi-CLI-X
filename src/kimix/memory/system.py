"""Complete Agent memory system."""

from typing import Dict, List

from kimix.memory.types import MemoryEntry, MemoryType
from kimix.memory.embedding import EmbeddingProvider
from kimix.memory.working_memory import WorkingMemory
from kimix.memory.short_term_memory import ShortTermMemory
from kimix.memory.long_term_memory import LongTermMemory


class AgentMemorySystem:
    """Complete Agent memory system."""

    def __init__(self, dim: int = 384, ltm_path: str = "agent_memory.json") -> None:
        self.embedding_provider = EmbeddingProvider(dim)

        # Three-tier memory architecture
        self.working = WorkingMemory(max_items=10)
        self.short_term = ShortTermMemory(max_size=100, ttl_seconds=3600)
        self.long_term = LongTermMemory(storage_path=ltm_path, dim=dim)

        # Config
        self.consolidation_interval = 100  # Consolidate every 100 interactions
        self.interaction_count = 0

    def perceive(
        self,
        observation: str,
        importance: float = 5.0,
        tags: List[str] | None = None,
        source: str = "environment",
    ) -> MemoryEntry:
        """Agent perceives input, stores in memory system."""
        entry = MemoryEntry(
            content=observation,
            memory_type=MemoryType.EPISODIC,
            importance=importance,
            tags=tags or [],
            source=source
        )

        # Enters both working and short-term memory
        self.working.add(entry)
        self.short_term.add(entry)

        self.interaction_count += 1

        # Periodic consolidation
        if self.interaction_count % self.consolidation_interval == 0:
            self._consolidate()

        return entry

    def recall(
        self,
        query: str,
        context_size: int = 5,
        use_working: bool = True,
        use_short: bool = True,
        use_long: bool = True,
        tag_filter: List[str] | None = None,
    ) -> Dict[str, List[MemoryEntry]]:
        """Multi-tier recall retrieval."""
        results: Dict[str, List[MemoryEntry]] = {
            'working': [],
            'short_term': [],
            'long_term': []
        }

        # Working memory: direct match of recent items
        if use_working:
            working_items = self.working.get_context(context_size)
            # Simple keyword match (working memory is usually small, return directly)
            results['working'] = working_items

        # Short-term memory: semantic search
        if use_short:
            results['short_term'] = self.short_term.search(
                query, self.embedding_provider, top_k=context_size
            )

        # Long-term memory: semantic search
        if use_long:
            results['long_term'] = self.long_term.retrieve(
                query, top_k=context_size, tag_filter=tag_filter
            )

        return results

    def remember(
        self,
        fact: str,
        importance: float = 8.0,
        tags: List[str] | None = None,
        memory_type: MemoryType = MemoryType.SEMANTIC,
    ) -> MemoryEntry:
        """Actively memorize fact/knowledge."""
        return self.long_term.store(
            content=fact,
            importance=importance,
            tags=tags or [],
            memory_type=memory_type,
            source="agent_learning"
        )

    def get_context_for_llm(self, query: str, max_tokens: int = 2000) -> str:
        """Generate context prompt for LLM (RAG style)."""
        memories = self.recall(query, context_size=5)

        context_parts: List[str] = []
        total_chars = 0

        # Priority: working > short-term > long-term
        for source, entries in [
            ("Current Focus", memories['working']),
            ("Recent Events", memories['short_term']),
            ("Relevant Knowledge", memories['long_term'])
        ]:
            if not entries:
                continue

            section = f"\n=== {source} ===\n"
            for entry in entries:
                item = f"- [{entry.memory_type.value}] {entry.content}\n"
                if total_chars + len(section) + len(item) > max_tokens:
                    break
                section += item

            context_parts.append(section)
            total_chars += len(section)

        return "\n".join(context_parts)

    def _consolidate(self) -> None:
        """Execute memory consolidation."""
        self.long_term.consolidate(self.short_term, threshold=6.0)
        self.short_term.clear_expired()

    def reflect(self) -> str:
        """Generate memory system status report."""
        report = f"""
Memory System Status Report:
===========================
Working Memory: {len(self.working.items)} items (capacity: {self.working.max_items})
Short-term Memory: {len(self.short_term.buffer)} items (capacity: {self.short_term.max_size})
Long-term Memory: {len(self.long_term.entries)} items
Interactions: {self.interaction_count}
        """
        return report
