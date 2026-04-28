import tempfile

from pathlib import Path

from kimix.utils.session import _create_session_async, close_session_async
from kimix.utils.prompt import prompt_async
from kimi_cli.vfs.core import VFS, merge

_ALL_VFS_PATH: dict[str, Path] = dict()

async def execute_swarm(prompt_str: str, vfs_path: Path | None) -> str:
    session = None
    try:
        session = await _create_session_async(
            vfs_path=vfs_path
        )
        custom_data = session.get_custom_data()
        assert custom_data is not None
        await prompt_async(prompt_str, session)
        summary: str = ''
        from kimix.base import generate_memory
        lines = []
        def export_func(text: str, is_thinking: bool) -> None:
            if not is_thinking:
                lines.append(text)
        await prompt_async(generate_memory, session, info_print=False, output_function=export_func)
        if lines:
            summary = '\n'.join(lines)
    finally:
        if session is not None:
            await close_session_async(session)
    return summary

async def merge_vfs_paths() -> Path | None:
    if not _ALL_VFS_PATH:
        return None

    merged_path = Path(tempfile.mkdtemp(prefix="swarm_merged_"))

    node_ids: list[str] = []
    vfs_instances: list[VFS] = []
    for node_id, vfs_path in _ALL_VFS_PATH.items():
        if vfs_path and vfs_path.exists():
            node_ids.append(node_id)
            vfs_instances.append(VFS(virtual_root=vfs_path, work_dir=merged_path))

    if not vfs_instances:
        _ALL_VFS_PATH.clear()
        return merged_path

    conflicts, _applied = merge(*vfs_instances, apply=True)

    if conflicts:
        session = None
        try:
            session = await _create_session_async()
            for rel_path, versions in conflicts.items():
                conflict_prompt = f"Merge conflict for file `{rel_path}`.\nMultiple versions exist from different swarm nodes:\n"
                for idx, content_bytes in versions:
                    node_id = node_ids[idx]
                    try:
                        content = content_bytes.decode('utf-8', errors='replace')
                    except Exception:
                        content = '<binary or unreadable>'
                    conflict_prompt += f"\n--- Version from {node_id} ---\n{content}\n"
                conflict_prompt += f"\nPlease produce the final merged content for `{rel_path}`. Output only the file content, no explanations."

                lines = []
                def capture(text: str, is_thinking: bool) -> None:
                    if not is_thinking:
                        lines.append(text)

                await prompt_async(conflict_prompt, session, info_print=False, output_function=capture)
                merged_content = '\n'.join(lines) if lines else ''
                dst = merged_path / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(merged_content, encoding='utf-8', errors='replace')
        finally:
            if session is not None:
                await close_session_async(session)

    _ALL_VFS_PATH.clear()
    return merged_path