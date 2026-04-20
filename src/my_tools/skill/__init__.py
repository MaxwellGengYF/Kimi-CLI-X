"""Text file indexer tool using FAISS for semantic search."""

import hashlib
import os
import sys
import re
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Dict, Any, ClassVar
from dataclasses import dataclass

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from kimi_cli.tools import SkipThisTool
from pydantic import BaseModel, Field


def _get_text_search_index() -> Any:
    """Lazy import of TextSearchIndex to avoid hard faiss dependency at import time."""
    from .faiss.text_search import TextSearchIndex
    return TextSearchIndex


# Supported text file extensions for indexing
SUPPORTED_TEXT_EXTENSIONS = frozenset([
    ".md", ".txt", "dockerfile", "makefile", "cmakelists.txt", "license", "readme",
    "changelog", "contributing", "authors", "copying", "notice",
    "patents", "version", ".toml", ".yaml", ".yml", ".json", ".xml",
    ".ini", ".cfg", ".conf", ".config"
])


@dataclass
class IndexedCollection:
    """Represents an indexed collection of files."""
    directory: str
    file_count: int
    chunk_count: int
    pipeline: Any  # RAGPipeline instance


class IndexerParams(BaseModel):
    """Parameters for the indexer tool."""

    query: str = Field(
        description="Search keywords (keywords only, not sentences)."
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top results to return."
    )
    content: bool = Field(
        default=False,
        description="Return full content of matched files."
    )
    negative: Optional[str] = Field(
        default=None,
        description="Optional keywords to penalize in search results (exclude results matching these keywords)."
    )


class SkillAnalyzer(CallableTool2[Any]):
    """Indexer tool for semantic search over text files."""

    params: type[BaseModel] = IndexerParams
    name: str = "SkillAnalyzer"
    description: str = "A powerful search and retrieve relevant tool."
    COLLECTION_NAME: ClassVar[str] = "work_dir_files"
    PERSIST_DIR: ClassVar[str] = ".cache/chroma_db"
    _collection_cache: ClassVar[dict[str, IndexedCollection]] = {}
    _index_cache: ClassVar[OrderedDict[str, Any]] = OrderedDict()
    _MAX_INDEX_CACHE_SIZE: ClassVar[int] = 3

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            self._text_search_index_cls = _get_text_search_index()
        except Exception:
            raise SkipThisTool()
        if not self._load_index():
            raise SkipThisTool()

    def _load_index(self, skill_path: list[Any] | None = None) -> bool:
        from kimix.agent_utils import get_skill_dirs
        SKILL_PATHS = skill_path if skill_path is not None else get_skill_dirs()
        search_paths = [str(Path(p).resolve()) for p in SKILL_PATHS]
        existing_paths = [p for p in search_paths if os.path.exists(p)]

        if not existing_paths:
            return False

        normalized = "|".join(sorted(os.path.abspath(p)
                              for p in existing_paths))
        cache_key = hashlib.md5(normalized.encode()).hexdigest()[:12]
        index_path = f".index_cache/{cache_key}"
        cache_dir = ".cache/text_search"

        index_cache_key = f"{cache_dir}:{index_path}"
        cached = False
        if index_cache_key in self._index_cache:
            index = self._index_cache.pop(index_cache_key)
            self._index_cache[index_cache_key] = index
            cached = True
        else:
            if len(self._index_cache) >= self._MAX_INDEX_CACHE_SIZE:
                oldest_key, _ = self._index_cache.popitem(last=False)
            index = self._text_search_index_cls(
                cache_dir=cache_dir, lazy_load=True)
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

    async def __call__(self, params: IndexerParams) -> ToolReturnValue:
        try:
            index = self._index
            search_paths = self._search_paths
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
                rel_path = r.file_path
                for base in search_bases:
                    try:
                        candidate = os.path.relpath(r.file_path, base)
                        if not candidate.startswith('..'):
                            rel_path = candidate
                            break
                    except ValueError:
                        pass

                line_text = r.line_text
                snippet = line_text[:200]
                output_lines.append(
                    f"{i}. [{r.score:.4f}] {rel_path}:{r.line_index + 1}")
                output_lines.append(
                    f"   {snippet}{'...' if len(line_text) > 200 else ''}")

                if params.content:
                    try:
                        with open(r.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            full_content = f.read(2000)
                        output_lines.append("\n   --- Full Content ---")
                        output_lines.append(
                            f"   {full_content}{'...' if len(full_content) == 2000 else ''}")
                        output_lines.append("   --- End Content ---\n")
                    except Exception:
                        pass

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
