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

        output_lines.append(f"Path: '{source}:{line_ref}'")
        # output_lines.append(f"**Line:** {line_ref}")

        if content:
            # Format content (first 500 chars)
            content_text = result.content[:500].strip()
            if len(result.content) > 500:
                content_text += "\n..."
            output_lines.append(f"\n\n{content_text}")

    return "\n".join(output_lines)


class SkillAnalyzerParams(BaseModel):
    """Parameters for the SkillAnalyzer tool."""

    query: str = Field(
        description="Search query to find relevant skills. Use ONLY keywords to describe what you're looking for.",
    )
    directory: str = Field(
        default=None,
        description="Directory to scan for skills. Defaults to current working directory. Skills are found in */SKILL.md pattern.",
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top matching skills to return (1-10).",
    )
    content: bool = Field(
        default=False,
        description="Return content in output.",
    )
    refresh: bool = Field(
        default=False,
        description="Force re-indexing of skills. Use when skills have been added or modified.",
    )


@dataclass
class IndexedCollection:
    """Container for an indexed collection with metadata."""
    pipeline: RAGPipeline
    directory: str
    skill_count: int
    chunk_count: int


class SkillAnalyzer(CallableTool2):
    name: str = "SkillAnalyzer"
    description: str = (
        "Analyze and search skills in the current work directory using semantic search. "
        "Indexes SKILL.md files and allows ONLY keywords queries to find relevant skills."
    )
    params: type[SkillAnalyzerParams] = SkillAnalyzerParams

    # Class-level cache for indexed collections
    _collection_cache: ClassVar[Dict[str, IndexedCollection]] = {}

    # Default collection name and persist directory
    COLLECTION_NAME: ClassVar[str] = "work_dir_skills"
    PERSIST_DIR: ClassVar[str] = ".skill_cache/chroma_db"

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

    async def __call__(self, params: SkillAnalyzerParams) -> ToolReturnValue:
        """Execute the skill analyzer tool.

        Args:
            params: Tool parameters

        Returns:
            ToolOk with formatted results or ToolError on failure
        """
        try:
            # Validate directory
            if params.directory is None:
                from agent_utils import _get_skill_dirs
                lst = _get_skill_dirs(False)
                if lst:
                    params.directory = lst[0]
                else:
                    params.directory = '.'
            # Ensure directory is converted to string first to handle KaosPath
            # then convert to standard Path to avoid __fspath__ issues
            dir_path = Path(str(params.directory))
            if not dir_path.exists():
                return ToolError(
                    message=f"Directory not found: {dir_path}",
                    output="",
                    brief="Directory not found",
                )

            if not dir_path.is_dir():
                return ToolError(
                    message=f"Path is not a directory: {dir_path}",
                    output="",
                    brief="Invalid directory",
                )

            # Index the directory
            # If path not in cache, force refresh to ensure it's indexed
            cache_key = self._get_cache_key(str(dir_path))
            try:
                indexed = self._index_directory(
                    str(dir_path),
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


class RAGParams(BaseModel):
    """Parameters for the RAG tool."""

    query: str = Field(
        description="Search query to find relevant content. Use ONLY keywords to describe what you're looking for.",
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Path to a file or directory to index and search. If a directory is provided, all text files within it will be indexed. Defaults to current working directory.",
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top matching results to return (1-10).",
    )
    content: bool = Field(
        default=False,
        description="Return content in output.",
    )
    refresh: bool = Field(
        default=False,
        description="Force re-indexing of the file. Use when the file has been modified.",
    )


@dataclass
class IndexedFile:
    """Container for an indexed file with metadata."""
    pipeline: RAGPipeline
    file_path: str
    chunk_count: int


class RAG(CallableTool2):
    name: str = "RAG"
    description: str = (
        "Perform semantic search on a text file using RAG. "
        "Indexes the file and allows ONLY keywords queries to find relevant content."
    )
    params: type[RAGParams] = RAGParams

    # Class-level cache for indexed files
    _file_cache: ClassVar[Dict[str, IndexedFile]] = {}

    # Default collection name and persist directory
    COLLECTION_NAME: ClassVar[str] = "rag_files"
    PERSIST_DIR: ClassVar[str] = ".skill_cache/rag_db"

    def _get_cache_key(self, file_path: str) -> str:
        """Generate a cache key for the given file."""
        abs_path = str(Path(file_path).resolve())
        return f"{self.COLLECTION_NAME}_{abs_path}"

    def _index_path(self, file_path_obj: Path, force_refresh: bool = False) -> IndexedFile:
        """Index the given file or directory.

        Args:
            file_path: Path to the file or directory to index
            force_refresh: Whether to force re-indexing

        Returns:
            IndexedFile with pipeline and metadata
        """
        if type(file_path_obj) is not Path:
            file_path_obj = Path(file_path_obj)

        # Resolve the path to get consistent absolute paths
        # This avoids Windows short path (MAXWEL~1) vs long path (maxwellgeng) mismatches
        try:
            file_path_obj = file_path_obj.resolve()
        except (OSError, FileNotFoundError):
            # If path doesn't exist, we can't resolve it - keep original for error message
            pass

        file_path = str(file_path_obj)
        cache_key = self._get_cache_key(file_path)

        # Check cache first
        if not force_refresh and cache_key in self._file_cache:
            cached = self._file_cache[cache_key]
            if cached.file_path == file_path:
                return cached

        # Initialize pipeline
        # Create a safe collection name that meets ChromaDB requirements:
        # - 3-512 characters from [a-zA-Z0-9._-]
        # - Must start and end with [a-zA-Z0-9]
        # Replace path separators and special chars with underscores
        safe_file_name = file_path.replace(
            "/", "_").replace("\\", "_").replace(":", "_")
        # Remove any characters that are not alphanumeric, dot, dash, or underscore
        safe_file_name = re.sub(r'[^a-zA-Z0-9._-]', '', safe_file_name)
        # Use hash for uniqueness and truncate to avoid length issues
        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:16]
        # Get the base name from the filename (last part of path) to keep it readable
        path_obj = Path(file_path)
        base_name = path_obj.stem if path_obj.stem else "file"
        # Clean the base name - remove invalid chars
        base_name = re.sub(r'[^a-zA-Z0-9._-]', '', base_name)
        base_name = base_name.strip('._-')
        if not base_name or len(base_name) < 2:
            base_name = "file"
        # Build collection name: prefix + safe base name + hash
        # Limit base_name to avoid too long names
        collection_name = f"{self.COLLECTION_NAME}_{base_name}_{file_hash}"
        # Final cleanup: ensure it starts and ends with alphanumeric
        collection_name = re.sub(r'^[^a-zA-Z0-9]+', '', collection_name)
        collection_name = re.sub(r'[^a-zA-Z0-9]+$', '', collection_name)

        pipeline = RAGPipeline(
            collection_name=collection_name,
            persist_directory=str(
                Path(self.PERSIST_DIR) / safe_file_name[:50]),
        )

        # Reset if refreshing
        if force_refresh:
            pipeline.reset()

        # Index the file or directory
        # Determine if it should be treated as a file or directory
        # If the path doesn't exist but looks like a file (has extension), treat as file
        is_file = file_path_obj.is_file()
        is_dir = file_path_obj.is_dir()

        # For non-existent paths, guess based on whether it has a file extension
        if not is_file and not is_dir:
            # Check if it looks like a file path (has extension)
            is_file = bool(file_path_obj.suffix)

        try:
            if is_file:
                result = pipeline.index_file(file_path_obj)
                chunk_count = result.total_chunks
            else:
                result = pipeline.index_directory(file_path_obj)
                chunk_count = result.total_chunks
        except Exception as e:
            pipeline.close()
            item_type = "file" if is_file else "directory"
            raise ValueError(f"Failed to index {item_type} '{file_path}': {e}")

        if chunk_count == 0:
            pipeline.close()
            item_type = "file" if is_file else "directory"
            raise ValueError(
                f"No content could be indexed from {item_type} '{file_path}'")

        indexed = IndexedFile(
            pipeline=pipeline,
            file_path=file_path,
            chunk_count=chunk_count,
        )

        # Cache the file
        self._file_cache[cache_key] = indexed

        return indexed

    async def __call__(self, params: RAGParams) -> ToolReturnValue:
        """Execute the RAG tool.

        Args:
            params: Tool parameters

        Returns:
            ToolOk with formatted results or ToolError on failure
        """
        try:
            # Validate file_path
            if params.file_path is None:
                params.file_path = "."

            file_path_obj = Path(params.file_path)
            if not file_path_obj.exists():
                return ToolError(
                    message=f"File not found: {params.file_path}",
                    output="",
                    brief="File not found",
                )

            # if not file_path_obj.is_file() and not file_path_obj.is_dir():
            #     return ToolError(
            #         message=f"Path is not a file: {params.file_path}",
            #         output="",
            #         brief="Path is not a file",
            #     )

            # Check if it's a file specifically (not a directory)
            # if file_path_obj.is_dir():
            #     return ToolError(
            #         message=f"Path is not a file: {params.file_path}",
            #         output="",
            #         brief="Path is not a file",
            #     )
            file_path_obj = file_path_obj.resolve()
            try:
                indexed = self._index_path(
                    file_path_obj,
                    force_refresh=params.refresh
                )
            except ValueError as e:
                error_msg = str(e)
                # Ensure error message starts with "Failed to index" for consistency
                if not error_msg.startswith("Failed to index"):
                    error_msg = f"Failed to index file: {error_msg}"
                return ToolError(
                    message=error_msg,
                    output="",
                    brief="Indexing failed",
                )
            except Exception as e:
                return ToolError(
                    message=f"Failed to index: {str(e)}",
                    output="",
                    brief="Indexing failed",
                )

            # Query the indexed file
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
            return ToolOk(output=_maybe_export_output(output))

        except Exception as e:
            return ToolError(
                message=f"Unexpected error: {str(e)}",
                output="",
                brief="Tool error",
            )
