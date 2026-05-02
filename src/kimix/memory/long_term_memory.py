"""Long-term memory: persistent storage with complex retrieval."""

import hashlib
import json
from typing import Dict, List, Optional

from kimix.memory.types import MemoryEntry, MemoryType
from kimix.memory.embedding import EmbeddingProvider


class LongTermMemory:
    """Long-term memory: persistent storage with complex retrieval."""

    def __init__(self, storage_path: Optional[str] = None, dim: int = 384) -> None:
        self.storage_path = storage_path or "ltm.json"
        self.dim = dim
        self.entries: Dict[str, MemoryEntry] = {}  # id -> entry
        self.index: Dict[str, List[str]] = {}      # tag -> entry_ids
        self.embedding_provider = EmbeddingProvider(dim)
        self._load()

    def _load(self) -> None:
        """Load from disk."""
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data:
                entry = MemoryEntry(
                    content=item['content'],
                    memory_type=MemoryType(item['memory_type']),
                    timestamp=item['timestamp'],
                    importance=item['importance'],
                    access_count=item.get('access_count', 0),
                    last_accessed=item.get('last_accessed', item['timestamp']),
                    embedding=item.get('embedding'),
                    tags=item.get('tags', []),
                    source=item.get('source', ''),
                    metadata=item.get('metadata', {})
                )
                self.entries[self._hash(entry.content)] = entry
                self._update_index(entry)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        """Persist to disk."""
        data = [e.to_dict() for e in self.entries.values()]
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _hash(self, content: str) -> str:
        """Generate content hash as ID."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _update_index(self, entry: MemoryEntry) -> None:
        """Update tag index."""
        entry_id = self._hash(entry.content)
        for tag in entry.tags:
            if tag not in self.index:
                self.index[tag] = []
            if entry_id not in self.index[tag]:
                self.index[tag].append(entry_id)

    def store(
        self,
        content: str,
        importance: float = 5.0,
        tags: Optional[List[str]] = None,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        source: str = "",
        metadata: Optional[Dict[str, object]] = None,
    ) -> MemoryEntry:
        """Store long-term memory."""
        entry = MemoryEntry(
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags or [],
            source=source,
            metadata=metadata or {}
        )

        # Generate embedding
        entry.embedding = self.embedding_provider.embed(content)

        entry_id = self._hash(content)
        self.entries[entry_id] = entry
        self._update_index(entry)
        self._save()

        return entry

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        tag_filter: Optional[List[str]] = None,
        min_importance: float = 0.0,
    ) -> List[MemoryEntry]:
        """Semantic retrieval from long-term memory."""
        if not self.entries:
            return []

        query_vec = self.embedding_provider.embed(query)

        candidates = list(self.entries.values())

        # Tag filter
        if tag_filter:
            filtered_ids = set()
            for tag in tag_filter:
                filtered_ids.update(self.index.get(tag, []))
            candidates = [self.entries[eid] for eid in filtered_ids if eid in self.entries]

        # Importance filter
        candidates = [e for e in candidates if e.importance >= min_importance]

        if not candidates:
            return []

        # Similarity sort
        scored = []
        for entry in candidates:
            if entry.embedding is None:
                entry.embedding = self.embedding_provider.embed(entry.content)
            sim = self.embedding_provider.similarity(query_vec, entry.embedding)
            # Combined score: similarity * effective importance
            final_score = sim * entry.get_effective_importance()
            scored.append((final_score, entry))

        scored.sort(reverse=True, key=lambda x: x[0])
        results = [entry for _, entry in scored[:top_k]]

        # Update access stats
        for entry in results:
            entry.touch()

        self._save()  # Persist access stat updates
        return results

    def consolidate(self, short_term: "ShortTermMemory", threshold: float = 7.0) -> None:
        """Memory consolidation: migrate high-value short-term to long-term."""
        from kimix.memory.short_term_memory import ShortTermMemory
        if not isinstance(short_term, ShortTermMemory):
            raise TypeError("short_term must be a ShortTermMemory instance")

        for entry in short_term.buffer[:]:  # Copy list to avoid iteration mutation
            if entry.get_effective_importance() >= threshold:
                # Migrate to long-term
                self.store(
                    content=entry.content,
                    importance=entry.importance,
                    tags=entry.tags,
                    memory_type=entry.memory_type,
                    source=entry.source,
                    metadata=entry.metadata
                )
                # Remove from short-term
                short_term.buffer.remove(entry)

    def forget(self, entry_id: str) -> None:
        """Active forgetting."""
        if entry_id in self.entries:
            entry = self.entries[entry_id]
            # Reduce importance instead of immediate deletion (simulates forgetting curve)
            entry.importance *= 0.5
            if entry.importance < 0.1:
                del self.entries[entry_id]
                # Clean index
                for tag in entry.tags:
                    if tag in self.index and entry_id in self.index[tag]:
                        self.index[tag].remove(entry_id)
            self._save()
