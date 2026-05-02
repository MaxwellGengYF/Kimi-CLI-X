"""Tests for WorkingMemory."""

import pytest

from kimix.memory.working_memory import WorkingMemory
from kimix.memory.types import MemoryEntry, MemoryType


class TestWorkingMemory:
    def test_add_and_get_context(self):
        wm = WorkingMemory(max_items=5)
        entry = MemoryEntry(content="item1", memory_type=MemoryType.EPISODIC)
        wm.add(entry)
        assert len(wm.items) == 1
        assert wm.get_context(1)[0].content == "item1"

    def test_max_capacity(self):
        wm = WorkingMemory(max_items=3)
        for i in range(5):
            wm.add(MemoryEntry(content=f"item{i}", memory_type=MemoryType.EPISODIC))
        assert len(wm.items) == 3
        context = wm.get_context(3)
        assert context[0].content == "item2"
        assert context[-1].content == "item4"

    def test_clear(self):
        wm = WorkingMemory(max_items=5)
        wm.add(MemoryEntry(content="item", memory_type=MemoryType.EPISODIC))
        wm.clear()
        assert len(wm.items) == 0
        assert wm.current_focus is None

    def test_summarize(self):
        wm = WorkingMemory(max_items=5)
        for i in range(3):
            wm.add(MemoryEntry(content=f"item{i}", memory_type=MemoryType.EPISODIC))
        summary = wm.summarize()
        assert "item0" in summary
        assert "item1" in summary
        assert "item2" in summary

    def test_empty_summarize(self):
        wm = WorkingMemory(max_items=5)
        assert wm.summarize() == ""

    def test_memory_type_set_to_working(self):
        wm = WorkingMemory(max_items=5)
        entry = MemoryEntry(content="test", memory_type=MemoryType.EPISODIC)
        wm.add(entry)
        assert entry.memory_type == MemoryType.WORKING
