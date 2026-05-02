"""Working memory: current conversation context, limited capacity."""

from collections import deque
from typing import List, Optional

from kimix.memory.types import MemoryEntry, MemoryType


class WorkingMemory:
    """Working memory: current conversation context, limited capacity."""

    def __init__(self, max_items: int = 10) -> None:
        self.max_items = max_items
        self.items: deque[MemoryEntry] = deque(maxlen=max_items)
        self.current_focus: Optional[str] = None

    def add(self, entry: MemoryEntry) -> None:
        """Add current context."""
        self.items.append(entry)
        entry.memory_type = MemoryType.WORKING

    def get_context(self, n: int = 5) -> List[MemoryEntry]:
        """Get recent n context items."""
        return list(self.items)[-n:]

    def clear(self) -> None:
        """Clear working memory."""
        self.items.clear()
        self.current_focus = None

    def summarize(self) -> str:
        """Generate current context summary."""
        if not self.items:
            return ""
        contents = [item.content for item in self.items]
        return " | ".join(contents[-3:])  # Simplified summary
