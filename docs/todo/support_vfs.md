# Plan: Integrate VFS into File Tools

## 1. Current State

### VFS (`kimi_cli/vfs/core.py`)
- `VFS(virtual_root, work_dir)` overlays a virtual directory on top of the work directory.
- Tracks dirty files in `_dirty_files: set[Path]`.
- `translate_path(path) -> Path`: returns virtual path if dirty, else original.
- `get(path, mark_dirty=True) -> Path`: copies file to virtual layer on first write access and returns the virtual path.
- `is_dirty(path) -> bool`.
- `merge(*vfs) -> dict[Path, list[tuple[int, bytes]]]`: conflict detection across multiple VFS instances.
- **Sync only**: operates on `pathlib.Path` with synchronous I/O.

### File Tools
| Tool | I/O Primitives | Needs VFS? |
|------|----------------|------------|
| `Glob` | `KaosPath.exists`, `is_dir`, `is_file`, `glob` | Read-only; should see virtual files |
| `Grep` | `os.walk`, `open`, `rg` subprocess on raw paths | Read-only; must search virtual overlay |
| `ReadFile` | `KaosPath.read_bytes`, `read_lines`, `read_text` | Read-only; must read virtual copy if dirty |
| `WriteFile` | `KaosPath.mkdir`, `write_text`, `append_text`, `read_text` | **Primary writer**; must mark dirty |
| `StrReplaceFile` | `KaosPath.stat`, `read_text`, `write_text` | Read+write; must mark dirty on write |

### Dependency Injection
- `KimiToolset._load_tool()` injects constructor args by matching annotations against `dependencies: dict[type, Any]`.
- `Runtime` is already injected. We can add `VFS` to the same `tool_deps` dict in `soul/agent.py`.

---

## 2. Design Decisions

### 2.1 Single VFS per Agent Runtime
Create one `VFS` instance per agent session:
```python
# soul/agent.py — in create_agent()
from kimi_cli.vfs import VFS
vfs = VFS(virtual_root=Path(tempfile.mkdtemp()), work_dir=Path(runtime.builtin_args.KIMI_WORK_DIR))
tool_deps[VFS] = vfs
```

### 2.2 Bridging VFS with `KaosPath`
`KaosPath` is an async wrapper around the filesystem. We cannot easily subclass it. Instead, add a lightweight helper that resolves a user-provided path through VFS **before** constructing the `KaosPath` used for I/O:

```python
async def resolve_vfs(path_str: str, vfs: VFS | None, *, for_write: bool = False) -> KaosPath:
    p = KaosPath(path_str).expanduser().canonical()
    if vfs is None:
        return p
    if for_write:
        # Ensure file is copied into virtual layer; returns virtual Path
        real = vfs.get(Path(p), mark_dirty=True)
    else:
        real = vfs.translate_path(Path(p))
    return KaosPath(real)
```

All file tools call `resolve_vfs(params.path, self._vfs, for_write=...)` at the top of `__call__`.

### 2.3 Workspace Validation Order
Current validation order:
1. Expand user / canonicalize
2. `is_within_workspace` check
3. I/O operations

New order with VFS:
1. Expand user / canonicalize
2. `is_within_workspace` check (on the **logical** path, before VFS translation)
3. `resolve_vfs` (translates to physical path)
4. I/O operations on translated `KaosPath`

This preserves security: we still reject paths outside the workspace; VFS only re-maps permitted paths.

### 2.4 `Grep` Special Case
`Grep` spawns `ripgrep`, which performs its own filesystem traversal. Two options:

**Option A – Virtual-aware fallback (Recommended)**
- When `vfs` is present and has dirty files, run `backup_grep` (pure-Python walker) instead of `ripgrep`.
- In `backup_grep`, iterate over `_collect_files` but replace each file path with `vfs.translate_path(file)` before reading.
- Pros: no temp-dir syncing, exact VFS semantics, simpler.
- Cons: slower for huge clean workspaces; acceptable because dirty set is usually small.

**Option B – Sync virtual root before `rg`**
- Before launching `rg`, mirror all dirty files from `virtual_root` into a temporary directory tree that matches the relative layout.
- Point `rg` at the temp tree.
- Pros: keeps `rg` fast path.
- Cons: complex, introduces stale-copy problems, extra disk I/O.

**Decision**: Implement Option A. If `vfs` has dirty files, use `backup_grep` with VFS translation. If no dirty files, keep existing `rg` fast path.

---

## 3. Per-Tool Changes

### 3.1 `Glob`
- Constructor: accept `VFS | None`.
- In `__call__`:
  - Resolve directory through VFS (`vfs.translate_path`).
  - The `dir_path.glob()` call on `KaosPath` will transparently see virtual files because the physical path is now inside `virtual_root`.
  - Virtual directories must exist; `Glob` calls `exists()` and `is_dir()` which will work if the directory was created by a previous write. If a virtual directory exists only because a nested file was written, `mkdir(parents=True)` during writes already ensures parent dirs exist.

### 3.2 `Grep`
- Constructor: accept `VFS | None`.
- In `__call__`:
  - If `self._vfs` is not None and `self._vfs._dirty_files` is non-empty:
    - Use `backup_grep(params)` with a VFS-aware `_read_file_text`.
  - Else: existing `rg` path.
- `_collect_files` / `_read_file_text` helper:
  ```python
  def _read_file_text_vfs(file_path: Path, vfs: VFS) -> str | None:
      real_path = vfs.translate_path(file_path)
      return _read_file_text(real_path)
  ```
  - `search_path` in `backup_grep` must also be translated: if the user greps `.`, translate to `vfs.translate_path(work_dir)` when dirty files exist.

### 3.3 `ReadFile`
- Constructor: accept `VFS | None`.
- In `__call__`:
  - After path validation, call `p = await resolve_vfs(params.path, self._vfs, for_write=False)`.
  - Continue with existing `read_bytes`, `read_lines`, etc.

### 3.4 `WriteFile`
- Constructor: accept `VFS | None`.
- In `__call__`:
  - After path validation, call `p = await resolve_vfs(params.path, self._vfs, for_write=True)`.
  - `p.parent.mkdir(parents=True, exist_ok=True)` already works because `resolve_vfs` returns a `KaosPath` pointing into `virtual_root`.
  - `write_text` / `append_text` write into virtual layer.
  - Diff generation (`build_diff_blocks`) uses `str(p)`; the displayed path should be the **logical** path (original), not the temp virtual path, to avoid confusing users.
    - Pass the original logical path string to diff / display blocks, while using the translated `KaosPath` for I/O.

### 3.5 `StrReplaceFile`
- Constructor: accept `VFS | None`.
- In `__call__`:
  - After path validation, call `p = await resolve_vfs(params.path, self._vfs, for_write=True)`.
  - `read_text` reads from virtual copy (or original if clean).
  - `write_text` writes back to virtual copy.
  - Same display-path concern as `WriteFile`: keep original logical path for diff blocks and messages.

---

## 4. Lifecycle & Persistence

### When is VFS merged back to disk?
The current `VFS` class has **no commit / merge-to-disk** operation. A higher-level orchestrator must eventually:
1. Call `merge(vfs_list)` to detect conflicts if multiple sub-agents have VFS instances.
2. Copy dirty files from `virtual_root` back to `work_dir`.

This is outside the scope of the file tools themselves, but the plan should note that `WriteFile` and `StrReplaceFile` no longer mutate the working directory directly. The caller (e.g., session teardown, or an explicit `VFSCommit` tool) is responsible for persistence.

### Rollback support
Because all writes go to `virtual_root`, the original files remain untouched until explicit merge. This gives us implicit rollback: discard `virtual_root` temp directory.

---

## 5. Implementation Order

1. **Add `VFS` to agent `tool_deps`** (`soul/agent.py`).
2. **Create `resolve_vfs` helper** in `tools/file/utils.py`.
3. **`WriteFile`**: integrate `resolve_vfs(..., for_write=True)`, keep logical path for display.
4. **`StrReplaceFile`**: same as WriteFile.
5. **`ReadFile`**: integrate `resolve_vfs(..., for_write=False)`.
6. **`Glob`**: translate search directory through VFS.
7. **`Grep`**: add dirty-file check and VFS-aware `backup_grep` path.
8. **Add tests** for VFS overlay: write via tool, read via tool, glob sees new file, grep finds text in virtual file.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `KaosPath` async methods on virtual paths may fail if `virtual_root` is on a different mount / permissions | Use `tempfile.mkdtemp()` under the same parent as `work_dir` when possible; ensure same filesystem. |
| `Grep` performance regression when dirty files exist | Dirty set is expected small; `backup_grep` is already the fallback when `rg` is missing. |
| Display paths show temp virtual paths to users | Always pass the original logical path to `build_diff_blocks` and tool messages. |
| Nested parent-dir creation for virtual files | `WriteFile` already calls `p.parent.mkdir(parents=True, exist_ok=True)`; virtual root handles it. |
| Plan-mode auto-approve checks plan file path equality | Compare against logical path, not translated virtual path. |
