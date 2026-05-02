"""Short-term memory: detailed current session records."""

import time
from typing import Dict, List

from kimix.memory.types import MemoryEntry, MemoryType
from kimix.memory.embedding import EmbeddingProvider


class ShortTermMemory:
    """Short-term memory: detailed current session records."""

    def __init__(self, max_size: int = 100, ttl_seconds: float = 3600) -> None:
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.buffer: List[MemoryEntry] = []
        self.access_pattern: Dict[str, int] = {}  # Access pattern log

    def add(self, entry: MemoryEntry) -> None:
        """Add memory to short-term buffer."""
        entry.memory_type = MemoryType.EPISODIC
        self.buffer.append(entry)

        # Capacity management: evict least important and oldest
        if len(self.buffer) > self.max_size:
            self._evict_least_valuable()

    def _evict_least_valuable(self) -> None:
        """Eviction policy: combined importance and recency."""
        if not self.buffer:
            return

        scores = [(i, e.get_effective_importance()) for i, e in enumerate(self.buffer)]
        scores.sort(key=lambda x: x[1])
        # Remove lowest score
        del self.buffer[scores[0][0]]

    def search(
        self, query: str, embedding_provider: EmbeddingProvider, top_k: int = 5
    ) -> List[MemoryEntry]:
        """Semantic search in short-term memory."""
        if not self.buffer:
            return []

        query_vec = embedding_provider.embed(query)

        # Compute similarity and sort
        scored = []
        for entry in self.buffer:
            if entry.embedding is None:
                entry.embedding = embedding_provider.embed(entry.content)
            sim = embedding_provider.similarity(query_vec, entry.embedding)
            # Combine with recency score
            final_score = sim * entry.get_effective_importance()
            scored.append((final_score, entry))

        scored.sort(reverse=True, key=lambda x: x[0])
        results = [entry for _, entry in scored[:top_k]]

        # Mark access
        for entry in results:
            entry.touch()

        return results

    def get_recent(self, n: int = 10) -> List[MemoryEntry]:
        """Get recent n entries."""
        return sorted(self.buffer, key=lambda x: x.timestamp, reverse=True)[:n]

    def clear_expired(self) -> None:
        """Clean expired memories."""
        now = time.time()
        self.buffer = [
            e for e in self.buffer
            if (now - e.timestamp) < self.ttl
        ]
