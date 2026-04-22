from typing import Any, List, Optional
import os
from pathlib import Path
import hashlib
from kimix.agent_utils import print_warning
from . import _globals
from .config import _ensure_text_search


def rag(
    query: str,
    file_path: Optional[str | Path] = None,
    top_k: int = 5,
    content: bool = False,
    refresh: bool = False,
    hybrid_search: bool = True,
    negative: Optional[str] = None
) -> List[Any]:
    """Perform semantic search using TextSearchIndex.

    This function uses an LRU cache to avoid re-indexing the same paths.

    Args:
        query: Search keywords (keywords only, not sentences)
        file_path: Directory or file path to search within (default: current directory)
        top_k: Number of top results to return (default: 5)
        content: Return full content of matched files (default: False)
        refresh: Force refresh the index (default: False)
        hybrid_search: Enable hybrid search combining semantic and keyword matching (default: True)
        negative: Optional keywords to penalize in search results

    Returns:
        List of SearchResult objects. Returns empty list if TextSearchIndex is not
        available, path does not exist, no documents found, or no results found.
    """
    try:
        _TextSearchIndex, _SearchResult = _ensure_text_search()
    except ImportError as e:
        print_warning(f"TextSearchIndex not available: {e}")
        return []

    # Determine the path to search
    search_path = file_path
    if search_path is None:
        search_path = "."

    # Resolve the path
    search_path = str(Path(search_path).resolve())

    # Check if path exists
    if not os.path.exists(search_path):
        print_warning(f"Path does not exist: {file_path}")
        return []

    # Create cache key from path
    normalized = os.path.abspath(search_path)
    cache_key_hash = hashlib.md5(normalized.encode()).hexdigest()
    index_path = f".index_cache/{cache_key_hash}"
    cache_dir = ".cache/text_search"

    # Use cached index if available and not refreshing (LRU cache)
    index_cache_key = f"{cache_dir}:{index_path}"
    cached = False
    index = None

    if not refresh and index_cache_key in _globals._index_cache:
        # Move to end (most recently used)
        index = _globals._index_cache.pop(index_cache_key)
        _globals._index_cache[index_cache_key] = index
        cached = True
    else:
        # Evict oldest entry if cache is full
        if len(_globals._index_cache) >= _globals._MAX_INDEX_CACHE_SIZE:
            oldest_key, _ = _globals._index_cache.popitem(last=False)
        # Create index with lazy loading and embedding cache
        index = _TextSearchIndex(cache_dir=cache_dir, lazy_load=True)
        _globals._index_cache[index_cache_key] = index

    # Try to load existing index or create new one
    save = False
    if os.path.exists(index_path) and not refresh:
        if not cached:
            index.load(index_path)
        # Remove files that no longer exist
        removed_files = index.remove_missing_files()
        if removed_files:
            save = True

        # Check for new/modified files and update incrementally
        if os.path.isdir(search_path):
            new_files = index.get_new_files(search_path)
            if new_files:
                for file_path_item in new_files:
                    index.add_file(file_path_item)
                save = True
        elif os.path.isfile(search_path):
            if index._is_file_modified(search_path):
                index.add_file(search_path)
                save = True
    else:
        # Fresh indexing (or forced refresh)
        if os.path.isdir(search_path):
            index.add_folder(search_path, parallel=True)
        elif os.path.isfile(search_path):
            index.add_file(search_path)
        # Save the index
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        save = True

    if save:
        index.save(index_path)

    # Check if index is empty
    stats = index.get_stats()
    if stats['total_documents'] == 0:
        print_warning("No documents found to index.")
        return []

    # Perform search based on hybrid_search parameter
    results: list[Any]
    if hybrid_search:
        results = index.hybrid_search(query, top_k=top_k, negative=negative)
    else:
        results = index.search(query, top_k=top_k, negative=negative)

    if not results:
        print_warning(f"No results found for query: '{query}'")
        return []

    # If content flag is True, include full file content in results
    if content:
        for r in results:
            try:
                with open(r.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    r.full_content = f.read()
            except Exception:
                r.full_content = None

    return results
