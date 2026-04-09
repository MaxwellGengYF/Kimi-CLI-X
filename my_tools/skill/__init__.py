"""Skill Analyzer tool using skill_rag for analyzing work directory skills."""

import os
from pathlib import Path
from typing import Optional, Dict, Any, ClassVar
from dataclasses import dataclass

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from skill_rag.pipeline import RAGPipeline, QueryResult
from skill_rag.loader import MarkdownLoader


class Params(BaseModel):
    """Parameters for the SkillAnalyzer tool."""

    query: str = Field(
        description="Search query to find relevant skills. Use natural language to describe what you're looking for.",
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
        "Indexes SKILL.md files and allows natural language queries to find relevant skills."
    )
    params: type[Params] = Params

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
        truncated = truncated.rstrip("._-")  # Remove trailing non-alphanumeric chars
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

    def _format_results(
        self,
        results: list[QueryResult],
        indexed: IndexedCollection,
        query: str,
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
        output_lines = [
            f"# Skill Analysis Results",
            f"",
            f"**Query:** {query}",
            f"**Indexed Skills:** {indexed.skill_count}",
            f"",
            f"---",
            f"",
        ]

        if not results:
            output_lines.append("No matching skills found for your query.")
            return "\n".join(output_lines)

        output_lines.append(f"**Found {len(results)} relevant skill(s):**")
        output_lines.append("")

        for i, result in enumerate(results, 1):
            # Extract metadata
            skill_name = result.metadata.get("name", "Unknown Skill")
            filename = result.metadata.get("filename", "SKILL.md")
            source = result.source
            start_line = result.start_line
            end_line = result.end_line

            # Format line reference
            line_ref = f"{start_line}" if start_line == end_line else f"{start_line}-{end_line}"

            # Format content preview (first 500 chars)
            content_preview = result.content[:500].strip()
            if len(result.content) > 500:
                content_preview += "\n\n... [content truncated]"

            output_lines.extend([
                f"**Result #{i}**",
                f"",
                f"**Skill:** {skill_name}",
                f"**Path:** `{source}`",
                f"**Line:** {line_ref}",
                f"**Relevance Score:** {1.0 - result.distance:.3f}",
            ])
            if content:
                output_lines.extend([
                    f"",
                    f"**Content Preview:**",
                    f"",
                    f"{content_preview}",
                    f"",
                    f"---",
                    f"",
                ])

        return "\n".join(output_lines)

    async def __call__(self, params: Params) -> ToolReturnValue:
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
                params.directory = lst[0]
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
            needs_refresh = cache_key not in self._collection_cache
            try:
                indexed = self._index_directory(
                    str(dir_path),
                    force_refresh=params.refresh or needs_refresh
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
            output = self._format_results(results, indexed, params.query, params.content)
            from my_tools.common import _maybe_export_output
            formatted_output = _maybe_export_output(output)
            return ToolOk(output=formatted_output, message=formatted_output)

        except Exception as e:
            return ToolError(
                message=f"Unexpected error: {str(e)}",
                output="",
                brief="Tool error",
            )
