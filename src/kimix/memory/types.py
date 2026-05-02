"""Memory types and data structures."""

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

import numpy as np


class MemoryType(Enum):
    """Memory type enumeration."""
    
    EPISODIC = "episodic"      # Event memory (specific experiences)
    SEMANTIC = "semantic"      # Semantic memory (facts/knowledge)
    PROCEDURAL = "procedural"  # Procedural memory (skills/methods)
    WORKING = "working"        # Working memory (current context)


@dataclass
class MemoryEntry:
    """Single memory entry."""

    content: str                          # Memory content
    memory_type: MemoryType               # Memory type
    timestamp: float = field(default_factory=time.time)
    importance: float = 1.0               # Importance score (0-10)
    access_count: int = 0                 # Access count
    last_accessed: float = field(default_factory=time.time)
    embedding: list[float] | None = None  # Vector embedding
    tags: list[str] = field(default_factory=list)
    source: str = ""                      # Source identifier
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_effective_importance(self) -> float:
        """Calculate effective importance (time decay + access frequency)."""
        days_old = (time.time() - self.timestamp) / 86400
        recency_factor = float(np.exp(-0.1 * days_old))  # Exponential decay

        # Access frequency boosts importance
        access_boost = min(self.access_count * 0.1, 2.0)

        return self.importance * recency_factor * (1 + access_boost)

    def touch(self) -> None:
        """Mark as accessed."""
        self.access_count += 1
        self.last_accessed = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            'memory_type': self.memory_type.value,
            'effective_importance': self.get_effective_importance()
        }
