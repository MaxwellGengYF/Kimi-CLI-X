import hashlib
import os
from dataclasses import dataclass
from collections import OrderedDict
from pathlib import Path
from typing import Any
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk
from pydantic import BaseModel, Field
from kimi_cli.tools import SkipThisTool
from typing import override
from kimi_cli.soul.approval import Approval

def _get_text_search_index():
    """Lazy import of TextSearchIndex to avoid hard faiss dependency at import time."""
    from my_tools.skill.faiss.text_search import TextSearchIndex
    return TextSearchIndex


# Supported text file extensions for indexing
SUPPORTED_TEXT_EXTENSIONS = frozenset([
    ".md", ".txt", "dockerfile", "makefile", "cmakelists.txt", "license", "readme",
    "changelog", "contributing", "authors", "copying", "notice",
    "patents", "version", ".toml", ".yaml", ".yml", ".json", ".xml",
    ".ini", ".cfg", ".conf", ".config"
])


class IndexerParams(BaseModel):
    """Parameters for the indexer tool."""
    query: str = Field(
        description="Search keywords/query."
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top results to return."
    )
    negative: str | None = Field(
        default=None,
        description="Optional keywords to penalize in search results (exclude results matching these keywords)."
    )


_MAX_INDEX_CACHE_SIZE = 3

class SkillRag(CallableTool2[IndexerParams]):
    """Indexer tool for semantic search over text files."""

    name: str = "SkillRag"
    description: str = "A powerful search and retrieve relevant tool for skill."
    _index_cache = OrderedDict()
    params: type[IndexerParams] = IndexerParams
    def _load_index(self, skill_path: list[Any] | None = None):
        from kimix.base import get_skill_dirs
        SKILL_PATHS = skill_path if skill_path is not None else get_skill_dirs(False)
        search_paths = [str(Path(p).resolve()) for p in SKILL_PATHS]
        existing_paths = [p for p in search_paths if os.path.exists(p)]

        if not existing_paths:
            return False

        normalized = "|".join(sorted(os.path.abspath(p)
                              for p in existing_paths))
        cache_key = hashlib.md5(normalized.encode()).hexdigest()
        index_path = f".index_cache/{cache_key}"
        cache_dir = ".cache/text_search"

        index_cache_key = f"{cache_dir}:{index_path}"
        cached = False
        if index_cache_key in self._index_cache:
            index = self._index_cache.pop(index_cache_key)
            self._index_cache[index_cache_key] = index
            cached = True
        else:
            if len(self._index_cache) >= _MAX_INDEX_CACHE_SIZE:
                oldest_key, _ = self._index_cache.popitem(last=False)
            index = self._text_search_index_cls(
                cache_dir=cache_dir)
            self._index_cache[index_cache_key] = index

        if os.path.exists(index_path):
            save = False
            if not cached:
                index.load(index_path)
            removed_files = index.remove_missing_files()
            if removed_files:
                save = True

            all_new_files = []
            for search_path in existing_paths:
                if os.path.isdir(search_path):
                    new_files = index.get_new_files(search_path)
                    if new_files:
                        all_new_files.extend(new_files)
                elif os.path.isfile(search_path):
                    if index._is_file_modified(search_path):
                        index.add_file(search_path)
                        all_new_files.append(search_path)

            if all_new_files:
                index.add_files_parallel(all_new_files)
                save = True
        else:
            for search_path in existing_paths:
                if os.path.isdir(search_path):
                    index.add_folder(search_path, parallel=True)
                elif os.path.isfile(search_path):
                    index.add_file(search_path)
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            save = True

        if save:
            index.save(index_path)

        self._index = index
        self._search_paths = existing_paths
        self._stats = index.get_stats()
        return True
    def __init__(self):
        super().__init__(self.name, self.description, self.params)
        import kimix.base as base
        if not base._enable_rag:
            raise SkipThisTool()
        try:
            self._text_search_index_cls = _get_text_search_index()
        except Exception as e:
            base.print_debug(f'RAG load failed, skipped: {str(e)}')
            raise SkipThisTool()
        base.print_debug('Loading RAG embedded model (can be slow)...')
        if not self._load_index():
            raise SkipThisTool()


    @override
    async def __call__(self, params: IndexerParams):
        try:
            index = self._index
            search_paths = self._search_paths
            if not self._load_index():
                return ToolOk(
                    output="No documents found to index.",
                    brief="No documents found",
                )
            stats = self._stats

            if stats['total_documents'] == 0:
                return ToolOk(
                    output="No documents found to index.",
                    brief="No documents found",
                )

            results = index.hybrid_search(
                params.query, top_k=params.top_k, negative=params.negative)

            if not results:
                return ToolOk(
                    output=f"No results found for query: '{params.query}'",
                    brief="No results found",
                )

            output_lines = []
            search_bases = [
                sp if os.path.isdir(sp) else os.path.dirname(sp)
                for sp in search_paths
            ]

            for i, r in enumerate(results, 1):
                rel_path = Path(r.file_path)
                try:
                    rel_path = rel_path.relative_to(Path('.').resolve())
                except ValueError as e:
                    pass
                line_text = r.line_text
                snippet = line_text[:100]
                rel_path = str(rel_path)
                output_lines.append(
                    f"{i}. [{r.score:.4f}] {rel_path}:{r.line_index + 1}")
                output_lines.append(
                    f"   {snippet}{'...' if len(line_text) > 100 else ''}")
            output_lines.append(
                f"\nIndexed {stats['total_files']} files, {stats['total_documents']} lines.")

            output_text = "\n".join(output_lines)

            return ToolOk(
                output=output_text,
                brief=f"Found {len(results)} results for '{params.query}'",
            )

        except Exception as e:
            return ToolError(
                message=f"Unexpected error: {str(e)}",
                output="",
                brief="Tool error",
            )
        
