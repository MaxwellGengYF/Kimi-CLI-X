from __future__ import annotations

import random
from pathlib import Path

import pytest

from kimi_cli.vfs.core import VFS, merge


def test_multi_vfs_shared_workdir(tmp_path: Path) -> None:
    """Multiple VFS instances share a work_dir and make independent changes."""
    wd = tmp_path / "work"
    wd.mkdir()

    # Create 4 VFS instances with independent virtual roots
    vfs_list = [
        VFS(tmp_path / f"virtual_{i}", wd)
        for i in range(4)
    ]

    # Seed work_dir with some base files
    (wd / "shared.txt").write_text("base_shared")
    (wd / "base.txt").write_text("base_base")

    # VFS 0: modifies shared.txt
    vfs_list[0].get(wd / "shared.txt")
    (vfs_list[0].virtual_root / "shared.txt").write_text("vfs0_edit")

    # VFS 1: modifies shared.txt differently -> conflict expected
    vfs_list[1].get(wd / "shared.txt")
    (vfs_list[1].virtual_root / "shared.txt").write_text("vfs1_edit")

    # VFS 2: modifies base.txt with same content as vfs3 -> auto-merge
    vfs_list[2].get(wd / "base.txt")
    vfs_list[3].get(wd / "base.txt")
    (vfs_list[2].virtual_root / "base.txt").write_text("same_edit")
    (vfs_list[3].virtual_root / "base.txt").write_text("same_edit")

    # VFS 0: creates a brand new file
    new_file_0 = vfs_list[0].virtual_root / "new0.txt"
    new_file_0.parent.mkdir(parents=True, exist_ok=True)
    new_file_0.write_text("new0")

    # VFS 1: creates another new file
    new_file_1 = vfs_list[1].virtual_root / "new1.txt"
    new_file_1.parent.mkdir(parents=True, exist_ok=True)
    new_file_1.write_text("new1")

    # Detect / auto-merge non-conflicts
    conflicts, applied = merge(*vfs_list, apply=True)

    # Verify non-conflicts were applied
    assert Path("new0.txt") in applied
    assert Path("new1.txt") in applied
    assert Path("base.txt") in applied
    assert (wd / "new0.txt").read_text() == "new0"
    assert (wd / "new1.txt").read_text() == "new1"
    assert (wd / "base.txt").read_text() == "same_edit"

    # Verify conflict remains
    assert Path("shared.txt") in conflicts
    assert (wd / "shared.txt").read_text() == "base_shared"

    # Resolve conflict randomly
    conflict_entries = conflicts[Path("shared.txt")]
    chosen_idx, chosen_data = random.choice(conflict_entries)
    dest = wd / "shared.txt"
    dest.write_bytes(chosen_data)

    # After manual resolution, clear dirty state for all VFS on this path
    for vfs in vfs_list:
        rel = Path("shared.txt")
        vfile = vfs.virtual_root / rel
        if vfile.exists():
            vfile.unlink()

    # Final state assertions
    assert (wd / "shared.txt").read_text() in {"vfs0_edit", "vfs1_edit"}
    assert not any(vfs.is_dirty(wd / "base.txt") for vfs in vfs_list)
    assert not any(vfs.is_dirty(wd / "new0.txt") for vfs in vfs_list)
    assert not any(vfs.is_dirty(wd / "new1.txt") for vfs in vfs_list)
