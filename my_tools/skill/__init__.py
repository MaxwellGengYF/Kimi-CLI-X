"""Skill Analyzer tool using skill_rag for analyzing work directory skills."""

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, ClassVar
from dataclasses import dataclass

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from skill_rag.pipeline import RAGPipeline, QueryResult
from skill_rag.loader import MarkdownLoader


def _format_results(
    results: list[QueryResult],
    content: bool
) -> str:
    """Format query results into a readable string.

    Args:
        results: List of QueryResult objects
        indexed: The indexed collection metadata
        query: Original query string

    Returns:
        Formatted output string
    """
    if not results:
        return "No matching skills found for your query."

    output_lines = []

    for result in results:
        source = result.source
        start_line = result.start_line
        end_line = result.end_line

        # Format line reference
        line_ref = f"{start_line}" if start_line == end_line else f"{start_line}-{end_line}"

        output_lines.append(f"Path:'{source}:{line_ref}' Score:{1.0 - result.distance:.2f}")
        # output_lines.append(f"**Line:** {line_ref}")

        if content:
            # Format content (first 500 chars)
            content_text = result.content[:500].strip()
            if len(result.content) > 500:
                content_text += "\n..."
            output_lines.append(f"\n\n{content_text}")

    return "\n".join(output_lines)


class IndexerParams(BaseModel):
    """Parameters for the indexer tool."""

    query: str = Field(
        description="Search keywords (keywords only, not sentences)."
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Directory or file path to search within."
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top results to return."
    )
    content: bool = Field(
        default=False,
        description="Return full content of matched skills."
    )
    refresh: bool = Field(
        default=False,
        description="Force re-indexing. Use when files have been added or modified.",
    )


@dataclass
class IndexedCollection:
    """Container for an indexed collection with metadata."""
    pipeline: RAGPipeline
    directory: str
    skill_count: int
    chunk_count: int


class indexer(CallableTool2):
    name: str = "indexer"
    description: str = "Search and retrieve relevant text using semantic similarity."
    params: type[IndexerParams] = IndexerParams

    # Class-level cache for indexed collections
    _collection_cache: ClassVar[Dict[str, IndexedCollection]] = {}

    # Default collection name and persist directory
    COLLECTION_NAME: ClassVar[str] = "work_dir_skills"
    PERSIST_DIR: ClassVar[str] = ".cache/chroma_db"

    def _find_skill_files(self, directory: Path) -> list[Path]:
        """Find all SKILL.md files in the directory.

        Searches for files matching pattern: */SKILL.md (case-sensitive)

        Args:
            directory: Root directory to search

        Returns:
            List of paths to SKILL.md files
        """
        skill_files = []

        # Ensure directory is a standard Path object (not KaosPath)
        # by converting through string to avoid __fspath__ issues
        if not isinstance(directory, Path):
            directory = Path(str(directory))

        # Search for all .md files recursively, then filter by exact name match
        # This ensures case-sensitivity on all platforms (Windows rglob is case-insensitive)
        for md_file in directory.rglob("*.md"):
            if md_file.is_file() and md_file.name == "SKILL.md":
                skill_files.append(md_file)

        return sorted(set(skill_files))

    def _get_cache_key(self, directory: str) -> str:
        """Generate a cache key for the given directory."""
        abs_path = str(Path(str(directory)).resolve())
        return f"{self.COLLECTION_NAME}_{abs_path}"

    def _index_directory(self, directory: str, force_refresh: bool = False) -> IndexedCollection:
        """Index skills in the given directory.

        Args:
            directory: Directory to index
            force_refresh: Whether to force re-indexing

        Returns:
            IndexedCollection with pipeline and metadata
        """
        dir_path = Path(str(directory)).resolve()
        cache_key = self._get_cache_key(directory)

        # Check cache first
        if not force_refresh and cache_key in self._collection_cache:
            cached = self._collection_cache[cache_key]
            if cached.directory == str(dir_path):
                return cached

        # Find skill files
        skill_files = self._find_skill_files(dir_path)

        if not skill_files:
            raise ValueError(
                f"No SKILL.md files found in '{directory}'. "
                "Skills are searched using pattern: */SKILL.md"
            )

        # Create unique collection name based on directory
        # Replace all invalid characters with underscore, ensure starts/ends with alphanumeric
        safe_dir_name = str(dir_path).replace(
            "/", "_").replace("\\", "_").replace(":", "_")
        # Take first 50 chars and ensure it ends with alphanumeric
        truncated = safe_dir_name[:50]
        # Remove trailing non-alphanumeric chars
        truncated = truncated.rstrip("._-")
        if not truncated[-1:].isalnum():
            truncated = truncated + "0"  # Ensure ends with alphanumeric
        collection_name = f"{self.COLLECTION_NAME}_{truncated}"

        # Initialize pipeline
        pipeline = RAGPipeline(
            collection_name=collection_name,
            persist_directory=str(Path(self.PERSIST_DIR) / safe_dir_name[:50]),
        )

        # Reset if refreshing
        if force_refresh:
            pipeline.reset()

        # Index all skill files
        total_chunks = 0
        for skill_file in skill_files:
            try:
                result = pipeline.index_file(skill_file)
                total_chunks += result.total_chunks
            except Exception as e:
                # Log error but continue with other files
                print(f"Warning: Failed to index {skill_file}: {e}")

        if total_chunks == 0:
            raise ValueError(
                "Failed to index any skills from found SKILL.md files")

        collection = IndexedCollection(
            pipeline=pipeline,
            directory=str(dir_path),
            skill_count=len(skill_files),
            chunk_count=total_chunks,
        )

        # Cache the collection
        self._collection_cache[cache_key] = collection

        return collection

    def _index_path(self, file_path_obj: Path, force_refresh: bool = False) -> IndexedCollection:
        """Index the given file or directory.

        Args:
            file_path_obj: Path to the file or directory to index
            force_refresh: Whether to force re-indexing

        Returns:
            IndexedCollection with pipeline and metadata
        """
        if type(file_path_obj) is not Path:
            file_path_obj = Path(file_path_obj)

        # Resolve the path to get consistent absolute paths
        try:
            file_path_obj = file_path_obj.resolve()
        except (OSError, FileNotFoundError):
            pass

        file_path = str(file_path_obj)
        is_file = file_path_obj.is_file()
        is_dir = file_path_obj.is_dir()

        # For non-existent paths, guess based on whether it has a file extension
        if not is_file and not is_dir:
            is_file = bool(file_path_obj.suffix)

        if is_file:
            # Index a single file (treat it as a skill file)
            return self._index_single_file(file_path_obj, force_refresh)
        else:
            # Index directory as before
            return self._index_directory(file_path, force_refresh)

    def _index_single_file(self, file_path_obj: Path, force_refresh: bool = False) -> IndexedCollection:
        """Index a single file as a skill file.

        Args:
            file_path_obj: Path to the file to index
            force_refresh: Whether to force re-indexing

        Returns:
            IndexedCollection with pipeline and metadata
        """
        file_path = str(file_path_obj.resolve())
        cache_key = self._get_cache_key(file_path)

        # Check cache first
        if not force_refresh and cache_key in self._collection_cache:
            cached = self._collection_cache[cache_key]
            if cached.directory == file_path:
                return cached

        # Create unique collection name based on file path
        safe_file_name = file_path.replace(
            "/", "_").replace("\\", "_").replace(":", "_")
        # Take first 50 chars and ensure it ends with alphanumeric
        truncated = safe_file_name[:50]
        truncated = truncated.rstrip("._-")
        if not truncated[-1:].isalnum():
            truncated = truncated + "0"
        collection_name = f"{self.COLLECTION_NAME}_{truncated}"

        # Initialize pipeline
        pipeline = RAGPipeline(
            collection_name=collection_name,
            persist_directory=str(Path(self.PERSIST_DIR) / safe_file_name[:50]),
        )

        # Reset if refreshing
        if force_refresh:
            pipeline.reset()

        # Index the single file
        try:
            result = pipeline.index_file(file_path_obj)
            total_chunks = result.total_chunks
        except Exception as e:
            pipeline.close()
            raise ValueError(f"Failed to index file '{file_path}': {e}")

        if total_chunks == 0:
            pipeline.close()
            raise ValueError(f"No content could be indexed from file '{file_path}'")

        collection = IndexedCollection(
            pipeline=pipeline,
            directory=file_path,
            skill_count=1,
            chunk_count=total_chunks,
        )

        # Cache the collection
        self._collection_cache[cache_key] = collection

        return collection

    async def __call__(self, params: IndexerParams) -> ToolReturnValue:
        try:
            # Validate file_path
            if params.file_path is None:
                params.file_path = '.'

            # Ensure path is converted to string first to handle KaosPath
            # then convert to standard Path to avoid __fspath__ issues
            file_path_obj = Path(str(params.file_path))
            if not file_path_obj.exists():
                return ToolError(
                    message=f"Path not found: {file_path_obj}",
                    output="",
                    brief="Path not found",
                )

            # Index the file or directory
            try:
                indexed = self._index_path(
                    file_path_obj,
                    force_refresh=params.refresh
                )
            except ValueError as e:
                return ToolError(
                    message=str(e),
                    output="",
                    brief="No skills found",
                )
            except Exception as e:
                return ToolError(
                    message=f"Failed to index skills: {str(e)}",
                    output="",
                    brief="Indexing failed",
                )

            # Query the indexed skills
            try:
                results = indexed.pipeline.query(
                    query_text=params.query,
                    top_k=params.top_k
                )
            except Exception as e:
                return ToolError(
                    message=f"Query failed: {str(e)}",
                    output="",
                    brief="Query failed",
                )

            # Format and return results
            output = _format_results(results, params.content)
            from my_tools.common import _maybe_export_output
            formatted_output = _maybe_export_output(output)
            return ToolOk(output=formatted_output, message=formatted_output)

        except Exception as e:
            return ToolError(
                message=f"Unexpected error: {str(e)}",
                output="",
                brief="Tool error",
            )
