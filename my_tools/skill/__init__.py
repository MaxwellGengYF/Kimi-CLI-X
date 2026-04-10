"""Text file indexer tool using FAISS for semantic search."""

import hashlib
import os
import sys
import re
from pathlib import Path
from typing import Optional, Dict, Any, ClassVar
from dataclasses import dataclass

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from .faiss.text_search import TextSearchIndex


# Supported text file extensions for indexing
SUPPORTED_TEXT_EXTENSIONS = frozenset([
    ".py", ".md", ".txt", ".js", ".ts", ".java", ".cpp", ".c", ".h",
    ".hpp", ".cc", ".cxx", ".go", ".rs", ".rb", ".php", ".swift",
    ".kt", ".kts", ".scala", ".groovy", ".json", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".dockerfile", ".makefile", ".cmake", ".gradle", ".properties",
    ".ini", ".cfg", ".conf", ".config", ".toml", ".sql", ".r",
    ".rmd", ".jl", ".lua", ".pl", ".pm", ".t", ".m", ".mm",
    ".cs", ".fs", ".fsx", ".vb", ".vbs", ".pas", ".pp", ".dpr",
    ".dart", ".elm", ".erl", ".hrl", ".ex", ".exs", ".hs", ".lhs",
    ".idr", ".lidr", ".nim", ".nims", ".ml", ".mli", ".zig", ".v",
    ".sv", ".vhd", ".vhdl", ".svh", ".e", ".tf", ".tfvars",
    ".graphql", ".gql", ".proto", ".thrift", ".avsc", ".avro",
    ".liquid", ".mustache", ".handlebars", ".hbs", ".ejs", ".pug",
    ".jade", ".slim", ".haml", ".erb", ".vue", ".svelte", ".astro",
    ".sol", ".vy", ".vyper", ".cairo", ".stark",
    # Special filenames (without extension)
    "dockerfile", "makefile", "cmakelists.txt", "license", "readme",
    "changelog", "contributing", "authors", "copying", "notice",
    "patents", "version", "package.json", "cargo.toml", "setup.py",
    "requirements.txt", "pyproject.toml", "gemfile", "composer.json",
    "pom.xml", "build.gradle", "go.mod", "go.sum", "cargo.lock",
    "packages.config", "project.clj", "build.boot", "deps.edn",
    "shadow-cljs.edn", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "pipfile", "pipfile.lock", "conda.yml", "environment.yml",
    "docker-compose.yml", "docker-compose.yaml", "dockerfile.dev",
    "makefile.am", "makefile.in", "configure.ac", "configure.in",
    "meson.build", "meson_options.txt", "xmake.lua", "CMakeLists.txt",
    ".gitignore", ".gitattributes", ".editorconfig", ".dockerignore",
])


@dataclass
class IndexedCollection:
    """Represents an indexed collection of files."""
    directory: str
    file_count: int
    chunk_count: int
    pipeline: Any  # RAGPipeline instance


def _format_results(results: list, content: bool = False) -> str:
    """Format search results into a human-readable string.
    
    Args:
        results: List of QueryResult objects
        content: Whether to include full content in output
        
    Returns:
        Formatted string with search results
    """
    if not results:
        return "No matching files found for your query."
    
    lines = []
    for r in results:
        # Calculate similarity score (1.0 - distance)
        score = 1.0 - (r.distance if hasattr(r, 'distance') else 0.0)
        
        # Format line range
        if hasattr(r, 'start_line') and hasattr(r, 'end_line'):
            if r.start_line == r.end_line:
                line_info = f"{r.start_line}"
            else:
                line_info = f"{r.start_line}-{r.end_line}"
        else:
            line_info = "?"
        
        # Get source path
        source = getattr(r, 'source', getattr(r, 'file_path', 'unknown'))
        
        lines.append(f"Path:'{source}:{line_info}' Score:{score:.2f}")
        
        if content and hasattr(r, 'content'):
            # Truncate content if too long
            content_text = r.content
            if len(content_text) > 500:
                content_text = content_text[:500] + "..."
            lines.append(f"  {content_text}")
    
    return "\n".join(lines)


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
        description="Return full content of matched files."
    )
    refresh: bool = Field(
        default=False,
        description="Force refresh the index."
    )
    hybrid_search: bool = Field(
        default=False,
        description="Enable hybrid search."
    )


class indexer(CallableTool2):
    """Indexer tool for semantic search over text files."""
    
    params: ClassVar[type[BaseModel]] = IndexerParams
    name: str = "indexer"
    description: str = "Search and retrieve relevant text using semantic similarity."
    COLLECTION_NAME: ClassVar[str] = "work_dir_files"
    PERSIST_DIR: ClassVar[str] = ".cache/chroma_db"
    _collection_cache: ClassVar[dict[str, IndexedCollection]] = {}

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if a file is a supported text file.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if the file is a supported text file, False otherwise
        """
        # Must be a file that exists
        if not file_path.is_file():
            return False
            
        # Get filename and extension
        file_name = file_path.name
        suffix = file_path.suffix.lower()
        file_name_lower = file_name.lower()
        
        # Check for special filenames without extension
        if file_name_lower in SUPPORTED_TEXT_EXTENSIONS:
            return True
            
        # Check extension (including the dot)
        if suffix in SUPPORTED_TEXT_EXTENSIONS:
            return True
            
        # Check filename without extension for special names
        if file_name_lower in ["dockerfile", "makefile", "license", "readme", 
                               "changelog", "contributing", "authors", "copying", 
                               "notice", "patents", "version"]:
            return True
            
        return False

    def _find_text_files(self, directory: str | Path) -> list[Path]:
        """Find all supported text files in a directory recursively.
        
        Args:
            directory: Directory to search
            
        Returns:
            Sorted list of Path objects for text files
        """
        dir_path = Path(directory)
        text_files = []
        
        for item in dir_path.rglob("*"):
            if self._is_text_file(item):
                text_files.append(item)
                
        return sorted(text_files)

    def _get_cache_key(self, path: str | Path) -> str:
        """Generate a cache key for a given path.
        
        Args:
            path: Path to generate cache key for
            
        Returns:
            Cache key string
        """
        path_obj = Path(path).resolve()
        return f"{self.COLLECTION_NAME}_{path_obj.as_posix()}"

    def _generate_collection_name(self, path: str | Path) -> str:
        """Generate a valid collection name from a path.
        
        Args:
            path: Path to generate collection name from
            
        Returns:
            Valid collection name string
        """
        # Get absolute path and hash it
        path_str = str(Path(path).resolve())
        path_hash = hashlib.md5(path_str.encode()).hexdigest()[:12]
        
        # Create base name
        base_name = f"{self.COLLECTION_NAME}_{path_hash}"
        
        # Ensure it's not too long (Chroma has a 63 char limit typically)
        if len(base_name) > 60:
            base_name = base_name[:60]
            
        return base_name

    def _index_directory(self, directory: str | Path, force_refresh: bool = False) -> IndexedCollection:
        """Index all text files in a directory.
        
        Args:
            directory: Directory to index
            force_refresh: Whether to force re-indexing
            
        Returns:
            IndexedCollection with indexing results
            
        Raises:
            ValueError: If no text files found or indexing fails
        """
        dir_path = Path(directory).resolve()
        cache_key = self._get_cache_key(dir_path)
        
        # Check cache unless force_refresh
        if not force_refresh and cache_key in self._collection_cache:
            return self._collection_cache[cache_key]
            
        # Find all text files
        files = self._find_text_files(dir_path)
        if not files:
            raise ValueError("No supported text files found in directory")
            
        # Clear cache if forcing refresh
        if force_refresh and cache_key in self._collection_cache:
            cached = self._collection_cache[cache_key]
            if hasattr(cached.pipeline, 'reset'):
                cached.pipeline.reset()
            del self._collection_cache[cache_key]
            
        # Generate collection name for RAGPipeline
        collection_name = self._generate_collection_name(dir_path)
        
        # For now, return a mock IndexedCollection
        # In real implementation, this would use RAGPipeline
        from unittest.mock import MagicMock
        mock_pipeline = MagicMock()
        mock_pipeline.index_file.return_value = MagicMock(total_chunks=5)
        
        total_chunks = 0
        for file_path in files:
            try:
                result = mock_pipeline.index_file(file_path)
                total_chunks += result.total_chunks
            except Exception:
                pass  # Continue with other files
                
        if total_chunks == 0:
            raise ValueError("Failed to index any content")
            
        collection = IndexedCollection(
            directory=str(dir_path),
            file_count=len(files),
            chunk_count=total_chunks,
            pipeline=mock_pipeline
        )
        
        self._collection_cache[cache_key] = collection
        return collection

    def _index_single_file(self, file_path: str | Path, force_refresh: bool = False) -> IndexedCollection:
        """Index a single text file.
        
        Args:
            file_path: Path to the file to index
            force_refresh: Whether to force re-indexing
            
        Returns:
            IndexedCollection with indexing results
            
        Raises:
            ValueError: If indexing fails
        """
        path = Path(file_path).resolve()
        cache_key = self._get_cache_key(path)
        
        # Check cache unless force_refresh
        if not force_refresh and cache_key in self._collection_cache:
            return self._collection_cache[cache_key]
            
        # Generate collection name for RAGPipeline
        collection_name = self._generate_collection_name(path)
        
        # For now, return a mock IndexedCollection
        from unittest.mock import MagicMock
        mock_pipeline = MagicMock()
        mock_pipeline.index_file.return_value = MagicMock(total_chunks=3)
        
        try:
            result = mock_pipeline.index_file(path)
            if result.total_chunks == 0:
                mock_pipeline.close()
                raise ValueError("No content could be indexed")
        except Exception as e:
            mock_pipeline.close()
            raise ValueError(f"Failed to index file: {e}")
            
        collection = IndexedCollection(
            directory=str(path),
            file_count=1,
            chunk_count=result.total_chunks,
            pipeline=mock_pipeline
        )
        
        self._collection_cache[cache_key] = collection
        return collection

    def _index_path(self, path: str | Path, force_refresh: bool = False) -> IndexedCollection:
        """Index a path (file or directory).
        
        Args:
            path: Path to index (file or directory)
            force_refresh: Whether to force re-indexing
            
        Returns:
            IndexedCollection with indexing results
        """
        path_obj = Path(path)
        
        # If path exists, check if it's a file or directory
        if path_obj.exists():
            if path_obj.is_file():
                return self._index_single_file(path_obj, force_refresh)
            else:
                return self._index_directory(path_obj, force_refresh)
        else:
            # Non-existent path: guess based on whether it has an extension
            if path_obj.suffix:
                return self._index_single_file(path_obj, force_refresh)
            else:
                return self._index_directory(path_obj, force_refresh)

    async def __call__(self, params: IndexerParams) -> ToolReturnValue:
        try:
            # Determine the path to search
            search_path = params.file_path
            if search_path is None:
                # Default to current working directory
                search_path = "."
            
            # Resolve the path
            search_path = str(Path(search_path).resolve())
            
            # Check if path exists
            if not os.path.exists(search_path):
                return ToolError(
                    message=f"Path does not exist: {params.file_path}",
                    output="",
                    brief=f"Path not found: {params.file_path}",
                )
            
            # Handle refresh parameter - clear cache for this path
            if params.refresh:
                cache_key = self._get_cache_key(search_path)
                if cache_key in self._collection_cache:
                    del self._collection_cache[cache_key]
            
            # Create cache key from path
            normalized = os.path.abspath(search_path)
            cache_key = hashlib.md5(normalized.encode()).hexdigest()[:12]
            index_path = f".index_cache/{cache_key}"
            cache_dir = ".cache/text_search"
            
            # Create index with lazy loading and embedding cache
            index = TextSearchIndex(cache_dir=cache_dir, lazy_load=True)
            
            # Try to load existing index or create new one
            if os.path.exists(index_path) and not params.refresh:
                index.load(index_path)
                
                # Check for new/modified files and update incrementally
                if os.path.isdir(search_path):
                    new_files = index.get_new_files(search_path)
                    if new_files:
                        for file_path in new_files:
                            print('add ' + str(file_path))
                            index.add_file(file_path)
                        print('save')
                        index.save(index_path)
                elif os.path.isfile(search_path):
                    if index._is_file_modified(search_path):
                        index.add_file(search_path)
                        index.save(index_path)
            else:
                # Fresh indexing (or forced refresh)
                if os.path.isdir(search_path):
                    index.add_folder(search_path, parallel=True)
                elif os.path.isfile(search_path):
                    index.add_file(search_path)
                
                # Save the index
                os.makedirs(os.path.dirname(index_path), exist_ok=True)
                index.save(index_path)
            
            # Check if index is empty
            stats = index.get_stats()
            if stats['total_documents'] == 0:
                return ToolOk(
                    output="No documents found to index.",
                    brief="No documents found",
                )
            
            # Perform search based on hybrid_search parameter
            if params.hybrid_search:
                results = index.hybrid_search(params.query, top_k=params.top_k)
            else:
                results = index.keyword_search(params.query, top_k=params.top_k)
            
            if not results:
                return ToolOk(
                    output=f"No results found for query: '{params.query}'",
                    brief="No results found",
                )
            
            # Format results
            output_lines = [f"Search results for '{params.query}':\n"]
            
            for i, r in enumerate(results, 1):
                rel_path = r.file_path
                try:
                    # Try to make path relative to search path
                    rel_path = os.path.relpath(r.file_path, search_path if os.path.isdir(search_path) else os.path.dirname(search_path))
                except ValueError:
                    pass  # Use absolute path if relpath fails
                
                output_lines.append(f"{i}. [{r.score:.4f}] {rel_path}:{r.line_index + 1}")
                output_lines.append(f"   {r.line_text[:200]}{'...' if len(r.line_text) > 200 else ''}")
                
                # If content flag is True, include full file content
                if params.content:
                    try:
                        with open(r.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            full_content = f.read()
                        output_lines.append(f"\n   --- Full Content ---")
                        output_lines.append(f"   {full_content[:2000]}{'...' if len(full_content) > 2000 else ''}")
                        output_lines.append(f"   --- End Content ---\n")
                    except Exception:
                        pass
                output_lines.append("")
            
            # Add summary
            output_lines.append(f"\nIndexed {stats['total_files']} files, {stats['total_documents']} lines.")
            
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
