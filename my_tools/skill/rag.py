"""RAG tool using skill_rag for semantic search on a single file."""

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, ClassVar
from dataclasses import dataclass

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from skill_rag.pipeline import RAGPipeline, QueryResult


class Params(BaseModel):
    """Parameters for the RAG tool."""
    
    query: str = Field(
        description="Search query to find relevant content. Use natural language to describe what you're looking for.",
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
        "Indexes the file and allows natural language queries to find relevant content."
    )
    params: type[Params] = Params
    
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
        safe_file_name = file_path.replace("/", "_").replace("\\", "_").replace(":", "_")
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
            persist_directory=str(Path(self.PERSIST_DIR) / safe_file_name[:50]),
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
            raise ValueError(f"No content could be indexed from {item_type} '{file_path}'")
        
        indexed = IndexedFile(
            pipeline=pipeline,
            file_path=file_path,
            chunk_count=chunk_count,
        )
        
        # Cache the file
        self._file_cache[cache_key] = indexed
        
        return indexed
    
    def _format_results(
        self, 
        results: list[QueryResult], 
        indexed: IndexedFile,
        query: str
    ) -> str:
        """Format query results into a readable string.
        
        Args:
            results: List of QueryResult objects
            indexed: The indexed file metadata
            query: Original query string
            
        Returns:
            Formatted output string
        """
        output_lines = [
            f"# RAG Search Results",
            f"",
            f"**Query:** {query}",
            f"**Indexed File:** `{indexed.file_path}`",
            f"**Total Chunks:** {indexed.chunk_count}",
            f"",
            f"---",
            f"",
        ]
        
        if not results:
            output_lines.append("No matching content found for your query.")
            return "\n".join(output_lines)
        
        output_lines.append(f"**Found {len(results)} relevant result(s):**")
        output_lines.append("")
        
        for i, result in enumerate(results, 1):
            # Extract metadata
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
                f"### {i}. Result",
                f"- **Source:** `{source}`",
                f"- **Line:** {line_ref}",
                f"- **Relevance Score:** {1.0 - result.distance:.3f}",
                f"**Content Preview:**",
                f"",
                f"{content_preview}",
                f"",
                f"---",
                f"",
            ])
        
        return "\n".join(output_lines)
    
    async def __call__(self, params: Params) -> ToolReturnValue:
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
            
            if not file_path_obj.is_file() and not file_path_obj.is_dir():
                return ToolError(
                    message=f"Path is not a file: {params.file_path}",
                    output="",
                    brief="Path is not a file",
                )
            
            # Check if it's a file specifically (not a directory)
            if file_path_obj.is_dir():
                return ToolError(
                    message=f"Path is not a file: {params.file_path}",
                    output="",
                    brief="Path is not a file",
                )
            file_path_obj = file_path_obj.resolve()
            # Index the file or directory
            # If path not in cache, force refresh to ensure it's indexed
            cache_key = self._get_cache_key(str(file_path_obj))
            needs_refresh = cache_key not in self._file_cache
            try:
                indexed = self._index_path(
                    file_path_obj, 
                    force_refresh=params.refresh or needs_refresh
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
            output = self._format_results(results, indexed, params.query)
            from my_tools.common import _maybe_export_output
            return ToolOk(output=_maybe_export_output(output))
            
        except Exception as e:
            return ToolError(
                message=f"Unexpected error: {str(e)}",
                output="",
                brief="Tool error",
            )
