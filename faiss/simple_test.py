"""
Simple interactive demo to search keywords in folders using TextSearchIndex.

Usage: python simple_test.py <folder_path> [folder_path2 ...]
       Then type keywords to search, or 'quit' to exit.
"""

import os
import sys
import hashlib
from pathlib import Path
from text_search import TextSearchIndex


def get_cache_key(folder_paths: list) -> str:
    """Create deterministic cache key from folder paths."""
    # Use absolute paths and sort for consistency
    normalized = "_".join(sorted(os.path.abspath(p) for p in folder_paths))
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def main():
    """Interactive keyword search in specified folders with auto-save/load."""
    if len(sys.argv) < 2:
        print("Error: Missing folder path argument(s).")
        print(f"Usage: python {sys.argv[0]} <folder_path> [folder_path2 ...]")
        sys.exit(1)
    
    folder_paths = sys.argv[1:]
    
    for folder_path in folder_paths:
        if not os.path.exists(folder_path):
            print(f"Error: Folder '{folder_path}' not found!")
            sys.exit(1)
    
    # Create cache key and path
    cache_key = get_cache_key(folder_paths)
    index_path = f".index_cache/{cache_key}"
    cache_dir = ".cache/text_search"
    
    # Create index with lazy loading and embedding cache
    index = TextSearchIndex(cache_dir=cache_dir, lazy_load=True)
    
    # Try to load existing index
    if os.path.exists(index_path):
        print(f"Loading cached index from {index_path}...")
        index.load(index_path)
        
        # Check for new/modified files and update incrementally
        total_new_lines = 0
        for folder_path in folder_paths:
            new_files = index.get_new_files(folder_path)
            if new_files:
                print(f"Found {len(new_files)} new/modified files in {folder_path}")
                for file_path in new_files:
                    lines_added = index.add_file(file_path)
                    total_new_lines += lines_added
                    if lines_added > 0:
                        print(f"  + {lines_added} lines from {Path(file_path)}")
        
        if total_new_lines > 0:
            print(f"Incremental update: added {total_new_lines} lines")
            # Save updated index
            index.save(index_path)
        else:
            print("All files up to date, no re-indexing needed.")
    else:
        # Fresh indexing with parallel processing
        print("Creating new index...")
        for folder_path in folder_paths:
            print(f"Indexing {folder_path}...")
            index.add_folder(folder_path, parallel=True)
        
        # Save the index
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        index.save(index_path)
    
    # Print stats
    stats = index.get_stats()
    print(f"\nIndexed {stats['total_files']} files, {stats['total_documents']} lines.")
    
    # Quick test search
    # results = index.keyword_search('shader', top_k=5)
    results = index.hybrid_search('shader', top_k=5)
    if not results:
        print(f"No results found for 'shader'")
    else:
        print(f"\nSample search for 'shader':")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.score:.4f}] {Path(r.file_path)}:{r.line_index + 1}")
            print(f"   {r.line_text[:100]}")


if __name__ == '__main__':
    main()
