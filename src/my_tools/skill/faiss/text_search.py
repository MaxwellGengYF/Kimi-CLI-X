"""
FAISS-based Text Search System

This module provides semantic text search capabilities using FAISS and sentence embeddings.
It can index text files (line by line) and perform similarity searches.
"""

import os
import hashlib
import json
import pickle
import logging
import warnings
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Union, Optional, Dict, Any, cast
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing as mp
import numpy as np
# Suppress SWIG-related deprecation warnings
warnings.filterwarnings("ignore", message="builtin type swigvarlink has no __module__ attribute", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="builtin type SwigPyPacked has no __module__ attribute", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="builtin type SwigPyObject has no __module__ attribute", category=DeprecationWarning)

# Lazy import of faiss
faiss = None

def _get_faiss() -> Any:
    """Lazy import of faiss."""
    global faiss
    if faiss is None:
        try:
            import faiss as _faiss
            faiss = _faiss
        except ImportError:
            raise ImportError(
                "faiss is required for RAG/search features. "
                "Install it with: uv pip install faiss-cpu"
            )
    return faiss

# Delay sentence_transformers import until needed
SentenceTransformer = None

def _get_sentence_transformer() -> Any:
    """Lazy import of SentenceTransformer."""
    global SentenceTransformer
    if SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer as ST
        SentenceTransformer = ST
    return SentenceTransformer

# Suppress transformers loading warnings
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)


@dataclass
class SearchResult:
    """Represents a search result with metadata."""
    file_path: str
    line_index: int
    line_text: str
    line_count: int
    score: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return asdict(self)


@dataclass
class DocumentLine:
    """Represents a single line from a document."""
    file_path: str
    line_index: int
    line_text: str
    line_count: int  # Total lines in the file


class EmbeddingCache:
    """Content-addressable cache for file embeddings."""
    
    def __init__(self, cache_dir: str = ".cache/text_search"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.cache_dir / "cache_index.json"
        self._cache_index = self._load_index()
    
    def _load_index(self) -> Dict[str, str]:
        """Load cache index mapping file hashes to cache file names."""
        if self._index_file.exists():
            try:
                with open(self._index_file, 'r') as f:
                    return cast(Dict[str, str], json.load(f))
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_index(self) -> None:
        """Save cache index to disk."""
        try:
            with open(self._index_file, 'w') as f:
                json.dump(self._cache_index, f)
        except IOError:
            pass
    
    def _get_file_hash(self, file_path: str) -> str:
        """Compute file content hash based on modification time and size."""
        try:
            stat = os.stat(file_path)
            hasher = hashlib.md5()
            hasher.update(f"{stat.st_mtime}_{stat.st_size}".encode())
            return hasher.hexdigest()
        except (OSError, IOError):
            return ""
    
    def get(self, file_path: str) -> Optional[np.ndarray]:
        """Retrieve cached embeddings if file hasn't changed."""
        file_hash = self._get_file_hash(file_path)
        if not file_hash:
            return None

        cache_key = f"{file_hash}.npy"
        cache_file = self.cache_dir / cache_key

        if cache_file.exists():
            try:
                embeddings: np.ndarray = np.load(cache_file)
                self._cache_index[file_path] = file_hash
                return embeddings
            except (IOError, ValueError):
                return None
        return None
    
    def put(self, file_path: str, embeddings: np.ndarray) -> None:
        """Cache embeddings for a file."""
        file_hash = self._get_file_hash(file_path)
        if not file_hash:
            return
        
        cache_key = f"{file_hash}.npy"
        cache_file = self.cache_dir / cache_key
        
        try:
            np.save(cache_file, embeddings)
            self._cache_index[file_path] = file_hash
            self._save_index()
        except IOError:
            pass
    
    def clear(self) -> None:
        """Clear all cached embeddings."""
        for cache_file in self.cache_dir.glob("*.npy"):
            try:
                cache_file.unlink()
            except IOError:
                pass
        self._cache_index = {}
        self._save_index()


class TextSearchIndex:
    """
    A FAISS-based text search index for semantic similarity search.
    
    Features:
    - Index text files line by line
    - Semantic search using sentence embeddings
    - Save/load index for reuse
    - Support for both file and folder paths
    """
    
    DEFAULT_MODEL = 'all-MiniLM-L6-v2'
    SUPPORTED_EXTENSIONS = {'.py', '.pyw', '.pyx', '.pxd',
                           '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
                           '.java', '.jsp',
                           '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.hxx',
                           '.go', '.rs', '.cs', '.kt', '.kts', '.scala', '.sc',
                           '.rb', '.erb', '.rake',
                           '.php', '.phtml',
                           '.swift', '.m', '.mm',
                           '.r', '.rmd', '.R',
                           '.pl', '.pm', '.t',
                           '.lua', '.luau',
                           '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
                           '.sql',
                           '.html', '.htm', '.xhtml', '.css', '.scss', '.sass', '.less',
                           '.md', '.markdown', '.mdx', '.txt', '.rst',
                           '.json', '.jsonc', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.config',
                           '.xml', '.svg', '.vbs',
                           '.dart', '.groovy', '.gvy', '.gradle',
                           '.hs', '.lhs', '.ml', '.mli', '.fs', '.fsx', '.fsi',
                           '.jl', '.clj', '.cljs', '.edn',
                           '.erl', '.hrl', '.ex', '.exs',
                           '.elm', '.coffee', '.litcoffee',
                           '.dockerfile', '.makefile', '.cmake', '.ninja',
                           '.proto', '.graphql', '.gql', '.prisma',
                           '.vue', '.svelte', '.astro',
                           '.lock', '.sum', '.mod'}
    
    def __init__(self, model_name: str = DEFAULT_MODEL, dimension: Optional[int] = None,
                 cache_dir: Optional[str] = None, lazy_load: bool = True):
        """
        Initialize the text search index.
        
        Args:
            model_name: Name of the sentence-transformers model to use
            dimension: Embedding dimension (auto-detected if None)
            cache_dir: Directory for embedding cache (None to disable)
            lazy_load: If True, delay model loading until first use
        """
        self.model_name = model_name
        self._dimension = dimension  # Store provided dimension for lazy loading
        self._model = None  # Lazy load
        self._lazy_load = lazy_load
        
        # FAISS index (use _index to avoid property conflict)
        self._index: Any = None  # faiss.Index when loaded
        
        # Document storage (maps FAISS id to document info)
        self.documents: List[DocumentLine] = []
        
        # Track indexed files to avoid duplicates
        self.indexed_files: set[str] = set()
        
        # Track file modification times for change detection
        self.file_metadata: Dict[str, Dict[str, Any]] = {}  # file_path -> {mtime, size}
        
        # Embedding cache
        self.embedding_cache = EmbeddingCache(cache_dir) if cache_dir else None
        
        # Initialize FAISS index
        self._init_index()
    
    
    @property
    def model(self) -> Any:
        """Lazy load the sentence transformer model."""
        if self._model is None:
            ST = _get_sentence_transformer()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
                model = ST(self.model_name, device='cpu')
            model.show_progress_bar = False
            # Set dimension if not already set
            if self._dimension is None:
                self._dimension = model.get_sentence_embedding_dimension()
            self._model = model
        return self._model
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension, loading model if necessary."""
        if self._dimension is None:
            self._dimension = self.model.get_sentence_embedding_dimension()
        return self._dimension
    
    @property
    def index(self) -> Any:
        """Access the FAISS index (lazy initialization)."""
        return self._index

    def _init_index(self) -> None:
        """Initialize the FAISS index."""
        # Use IndexFlatIP for cosine similarity (with normalized vectors)
        # or IndexFlatL2 for L2 distance
        # Index will be created lazily when first used
        self._index = None

    def _ensure_index(self) -> None:
        """Ensure FAISS index is initialized with correct dimension."""
        if self._index is None:
            self._index = _get_faiss().IndexFlatIP(self.dimension)
    
    def _normalize_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """Normalize vectors for cosine similarity."""
        _get_faiss().normalize_L2(vectors)
        return vectors
    
    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for a list of texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        embeddings = np.array(embeddings).astype('float32')
        return self._normalize_vectors(embeddings)
    
    def _is_text_file(self, file_path: str) -> bool:
        """Check if a file is a text file based on extension."""
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS
    
    def _read_text_file(self, file_path: str) -> List[str]:
        """
        Read a text file and return its lines.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            List of lines in the file
        """
        lines = []
        try:
            # Try UTF-8 first
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Warning: Could not read file {file_path}: {e}")
            return []
        
        # Strip newlines but keep empty lines for accurate indexing
        lines = [line.rstrip('\n\r') for line in lines]
        return lines
    
    def _collect_files(self, path: str) -> List[str]:
        """
        Collect all text files from a path (file or folder).
        
        Args:
            path: File or folder path
            
        Returns:
            List of file paths
        """
        path_obj = Path(path)
        files = []
        
        if path_obj.is_file():
            if self._is_text_file(str(path_obj)):
                files.append(str(path_obj.resolve()))
        elif path_obj.is_dir():
            for root, _, filenames in os.walk(path_obj):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    if self._is_text_file(file_path):
                        files.append(str(Path(file_path).resolve()))
        
        return files
    
    def add_file(self, file_path: str) -> int:
        """
        Add a single file to the index.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Number of lines added
        """
        file_path = str(Path(file_path).resolve())
        
        # Check if file needs re-indexing
        if file_path in self.indexed_files:
            if not self._is_file_modified(file_path):
                return 0  # File unchanged, skip
            else:
                # File modified, remove old entries
                self._remove_file_entries(file_path)
        
        lines = self._read_text_file(file_path)
        if not lines:
            # Track empty file to avoid re-processing
            self._update_file_metadata(file_path)
            self.indexed_files.add(file_path)
            return 0
        
        line_count = len(lines)
        
        # Filter out empty lines for embedding but keep track of their indices
        non_empty_lines = [(i, line) for i, line in enumerate(lines) if line.strip()]
        
        if not non_empty_lines:
            self._update_file_metadata(file_path)
            self.indexed_files.add(file_path)
            return 0
        
        indices, texts_tuple = zip(*non_empty_lines)
        texts = list(texts_tuple)

        # Try to get embeddings from cache
        embeddings = None
        if self.embedding_cache:
            embeddings = self.embedding_cache.get(file_path)
            if embeddings is not None and len(embeddings) != len(texts):
                # Cache invalid (different number of lines)
                embeddings = None

        # Compute embeddings if not cached
        if embeddings is None:
            embeddings = self._get_embeddings(texts)
            if self.embedding_cache:
                self.embedding_cache.put(file_path, embeddings)

        # Add to FAISS index
        self._ensure_index()
        assert self._index is not None
        self._index.add(embeddings)
        
        # Store document metadata
        for i, line_text in zip(indices, texts):
            self.documents.append(DocumentLine(
                file_path=file_path,
                line_index=i,
                line_text=line_text,
                line_count=line_count
            ))
        
        self._update_file_metadata(file_path)
        self.indexed_files.add(file_path)
        return len(non_empty_lines)
    
    def _is_file_modified(self, file_path: str) -> bool:
        """Check if a file has been modified since last indexed."""
        try:
            stat = os.stat(file_path)
            current_mtime = stat.st_mtime
            current_size = stat.st_size
            
            if file_path not in self.file_metadata:
                return True
            
            metadata = self.file_metadata[file_path]
            return (metadata.get('mtime') != current_mtime or 
                    metadata.get('size') != current_size)
        except (OSError, IOError):
            return True
    
    def _update_file_metadata(self, file_path: str) -> None:
        """Update stored metadata for a file."""
        try:
            stat = os.stat(file_path)
            self.file_metadata[file_path] = {
                'mtime': stat.st_mtime,
                'size': stat.st_size
            }
        except (OSError, IOError):
            pass
    
    def _remove_file_entries(self, file_path: str) -> None:
        """Remove all document entries for a file (for re-indexing)."""
        # Filter out documents from this file
        self.documents = [d for d in self.documents if d.file_path != file_path]
        self.indexed_files.discard(file_path)
        self.file_metadata.pop(file_path, None)

        # Rebuild FAISS index (unfortunately necessary since FAISS doesn't support deletion)
        if self.documents:
            all_texts = [d.line_text for d in self.documents]
            all_embeddings = self._get_embeddings(all_texts)
            self._init_index()
            self._ensure_index()
            assert self._index is not None
            self._index.add(all_embeddings)
    
    def remove_missing_files(self) -> List[str]:
        """
        Remove all entries for files that no longer exist on disk.
        
        Returns:
            List of file paths that were removed from the index
        """
        # Find files in index that no longer exist
        missing_files = [f for f in self.indexed_files if not os.path.exists(f)]
        
        if missing_files:
            for file_path in missing_files:
                self._remove_file_entries(file_path)
        
        return missing_files
    
    def get_new_files(self, folder_path: str) -> List[str]:
        """
        Get list of files that are new or modified since last indexing.
        
        Args:
            folder_path: Path to the folder
            
        Returns:
            List of file paths that need to be indexed
        """
        all_files = self._collect_files(folder_path)
        new_files = []
        
        for file_path in all_files:
            file_path = str(Path(file_path).resolve())
            if file_path not in self.indexed_files or self._is_file_modified(file_path):
                new_files.append(file_path)
        
        return new_files
    
    def add_folder(self, folder_path: str, parallel: bool = True, 
                   max_workers: Optional[int] = None, batch_size: int = 256) -> int:
        """
        Add all text files from a folder to the index.
        
        Args:
            folder_path: Path to the folder
            parallel: If True, use parallel processing for file reading and batch embedding
            max_workers: Maximum number of worker threads (default: auto)
            batch_size: Batch size for embedding computation
            
        Returns:
            Total number of lines added
        """
        if parallel:
            return self.add_folder_parallel(folder_path, max_workers, batch_size)
        
        files = self._collect_files(folder_path)
        total_lines = 0
        
        for file_path in files:
            lines_added = self.add_file(file_path)
            total_lines += lines_added
        
        return total_lines
    
    def add_files_parallel(self, file_paths: List[str], max_workers: Optional[int] = None,
                           batch_size: int = 256) -> int:
        """
        Add multiple files using parallel processing and batch embedding.

        Args:
            file_paths: List of file paths to add
            max_workers: Maximum number of worker threads (default: min(32, cpu_count + 4))
            batch_size: Batch size for embedding computation

        Returns:
            Total number of lines added
        """
        if max_workers is None:
            max_workers = min(32, (mp.cpu_count() or 1) + 4)

        # Filter out already indexed files that haven't changed
        files_to_process = []
        for file_path in file_paths:
            file_path = str(Path(file_path).resolve())
            if file_path not in self.indexed_files or self._is_file_modified(file_path):
                files_to_process.append(file_path)

        if not files_to_process:
            return 0

        # Phase 1: Parallel file reading
        def read_file_task(file_path: str) -> Optional[tuple[str, list[str], list[tuple[int, str]], int]]:
            """Read a file and return its contents."""
            try:
                lines = self._read_text_file(file_path)
                if not lines:
                    return (file_path, [], [], 0)

                line_count = len(lines)
                non_empty = [(i, line) for i, line in enumerate(lines) if line.strip()]
                return (file_path, lines, non_empty, line_count)
            except Exception:
                return None

        file_contents = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(read_file_task, f): f for f in files_to_process}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    file_path, lines, non_empty, line_count = result
                    file_contents[file_path] = (lines, non_empty, line_count)

        # Phase 2: Collect all texts and check cache
        all_texts: List[str] = []
        all_metadata = []  # (file_path, line_index, line_count)
        files_needing_embeddings: Dict[str, Any] = {}  # file_path -> dict of metadata

        batch_start_idx = 0
        for file_path, (lines, non_empty, line_count) in file_contents.items():
            if not non_empty:
                self._update_file_metadata(file_path)
                self.indexed_files.add(file_path)
                continue

            indices, texts_tuple = zip(*non_empty)
            texts = list(texts_tuple)

            # Try cache first
            cached_embeddings = None
            if self.embedding_cache:
                cached_embeddings = self.embedding_cache.get(file_path)
                if cached_embeddings is not None and len(cached_embeddings) != len(texts):
                    cached_embeddings = None

            if cached_embeddings is not None:
                # Use cached embeddings directly
                self._ensure_index()
                assert self._index is not None
                self._index.add(cached_embeddings)
                for i, line_text in zip(indices, texts):
                    self.documents.append(DocumentLine(
                        file_path=file_path,
                        line_index=i,
                        line_text=line_text,
                        line_count=line_count
                    ))
                self._update_file_metadata(file_path)
                self.indexed_files.add(file_path)
            else:
                # Need to compute embeddings
                files_needing_embeddings[file_path] = {
                    'indices': indices,
                    'texts': texts,
                    'line_count': line_count,
                    'batch_start': batch_start_idx
                }
                batch_start_idx += len(texts)
                all_texts.extend(texts)
                all_metadata.extend([(file_path, idx, line_count) for idx in indices])

        if not all_texts:
            return sum(len(file_contents[f][1]) for f in file_contents if file_contents[f][1])

        # Phase 3: Batch embedding computation
        all_embeddings = []
        for i in range(0, len(all_texts), batch_size):
            batch = all_texts[i:i + batch_size]
            embeddings = self._get_embeddings(batch)
            all_embeddings.append(embeddings)

        if all_embeddings:
            combined_embeddings = np.vstack(all_embeddings)

            # Phase 4: Add to FAISS index and store metadata
            self._ensure_index()
            assert self._index is not None
            self._index.add(combined_embeddings)

            # Cache embeddings per file and store metadata
            idx_offset = 0
            for file_path, data in files_needing_embeddings.items():
                texts = data['texts']
                indices = data['indices']
                line_count = data['line_count']
                num_lines = len(texts)

                # Extract embeddings for this file
                file_embeddings = combined_embeddings[idx_offset:idx_offset + num_lines]
                idx_offset += num_lines

                # Cache the embeddings
                if self.embedding_cache:
                    self.embedding_cache.put(file_path, file_embeddings)

                # Store document metadata
                for i, line_text in zip(indices, texts):
                    self.documents.append(DocumentLine(
                        file_path=file_path,
                        line_index=i,
                        line_text=line_text,
                        line_count=line_count
                    ))

                self._update_file_metadata(file_path)
                self.indexed_files.add(file_path)

        total_lines = sum(len(file_contents[f][1]) for f in file_contents if file_contents[f][1])
        return total_lines

    def add_folder_parallel(self, folder_path: str, max_workers: Optional[int] = None,
                           batch_size: int = 256) -> int:
        """
        Add folder using parallel processing and batch embedding.

        Args:
            folder_path: Path to the folder
            max_workers: Maximum number of worker threads (default: min(32, cpu_count + 4))
            batch_size: Batch size for embedding computation

        Returns:
            Total number of lines added
        """
        files = self._collect_files(folder_path)
        return self.add_files_parallel(files, max_workers, batch_size)
    
    def add_path(self, path: str) -> int:
        """
        Add a file or folder to the index.
        
        Args:
            path: File or folder path
            
        Returns:
            Number of lines added
        """
        path_obj = Path(path)
        if path_obj.is_file():
            return self.add_file(path)
        elif path_obj.is_dir():
            return self.add_folder(path)
        else:
            raise ValueError(f"Path does not exist: {path}")
    
    def search(self, query: str, top_k: int = 5, negative: Optional[str] = None) -> List[SearchResult]:
        """
        Search for similar lines using semantic similarity.
        
        Args:
            query: Search query (keyword or sentence)
            top_k: Number of top results to return
            negative: Optional negative query to penalize similar results
            
        Returns:
            List of search results sorted by relevance
        """
        self._ensure_index()
        assert self._index is not None
        if self._index.ntotal == 0:
            return []

        # Get query embedding
        query_embedding = self._get_embeddings([query])

        # Get negative embedding if provided
        negative_embedding = None
        if negative is not None and negative.strip():
            negative_embedding = self._get_embeddings([negative])
        # Search in FAISS
        scores, indices = self._index.search(query_embedding, min(top_k, self._index.ntotal))
        
        # Build results
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            
            doc = self.documents[idx]
            final_score = float(score)

            # Calculate negative distance and subtract from score
            if negative_embedding is not None:
                # Get the document embedding for this result
                assert self._index is not None
                doc_embedding = self._index.reconstruct(int(idx))
                # Calculate cosine similarity with negative query (both are normalized)
                negative_sim = float(np.dot(doc_embedding, negative_embedding[0]))
                # Subtract negative similarity from score
                final_score = final_score - negative_sim
            
            results.append(SearchResult(
                file_path=doc.file_path,
                line_index=doc.line_index,
                line_text=doc.line_text,
                line_count=doc.line_count,
                score=final_score
            ))
        
        # Re-sort results by adjusted score
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def keyword_search(self, keyword: str, top_k: int = 5, negative: Optional[str] = None) -> List[SearchResult]:
        """
        Search for lines containing a keyword (case-insensitive).
        
        Args:
            keyword: Keyword to search for
            top_k: Maximum number of results to return
            negative: Optional negative keyword to penalize results containing it
            
        Returns:
            List of search results
        """
        keyword_lower = keyword.lower()
        negative_lower = negative.lower().strip() if negative else None
        results = []
        
        for doc in self.documents:
            if keyword_lower in doc.line_text.lower():
                # Calculate a simple relevance score based on occurrence
                count = doc.line_text.lower().count(keyword_lower)
                score = min(count * 0.3, 1.0)
                
                # Calculate negative distance and subtract from score
                if negative_lower:
                    negative_count = doc.line_text.lower().count(negative_lower)
                    negative_score = min(negative_count * 0.3, 1.0)
                    score = score - negative_score
                
                results.append(SearchResult(
                    file_path=doc.file_path,
                    line_index=doc.line_index,
                    line_text=doc.line_text,
                    line_count=doc.line_count,
                    score=score
                ))
        # Sort by score and return top_k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def hybrid_search(self, query: str, top_k: int = 5, semantic_weight: float = 0.7, negative: Optional[str] = None) -> List[SearchResult]:
        """
        Perform hybrid search combining semantic and keyword matching.
        
        Args:
            query: Search query
            top_k: Number of results to return
            semantic_weight: Weight for semantic scores (0-1), keyword gets (1-weight)
            negative: Optional negative query to penalize similar results
            
        Returns:
            List of search results
        """
        # Get semantic results with negative query
        semantic_results = self.search(query, top_k=top_k * 2, negative=negative)
        
        # Get keyword results with negative keyword
        keyword_results = self.keyword_search(query, top_k=top_k * 2, negative=negative)
        
        # Combine results
        all_results: Dict[str, SearchResult] = {}
        
        for r in semantic_results:
            key = f"{r.file_path}:{r.line_index}"
            all_results[key] = SearchResult(
                file_path=r.file_path,
                line_index=r.line_index,
                line_text=r.line_text,
                line_count=r.line_count,
                score=r.score * semantic_weight
            )
        
        for r in keyword_results:
            key = f"{r.file_path}:{r.line_index}"
            if key in all_results:
                # Combine scores
                existing = all_results[key]
                all_results[key] = SearchResult(
                    file_path=r.file_path,
                    line_index=r.line_index,
                    line_text=r.line_text,
                    line_count=r.line_count,
                    score=existing.score + r.score * (1 - semantic_weight)
                )
            else:
                all_results[key] = SearchResult(
                    file_path=r.file_path,
                    line_index=r.line_index,
                    line_text=r.line_text,
                    line_count=r.line_count,
                    score=r.score * (1 - semantic_weight)
                )
        
        # Sort and return top_k
        results = sorted(all_results.values(), key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        self._ensure_index()
        return {
            'total_documents': len(self.documents),
            'total_files': len(self.indexed_files),
            'indexed_files': list(self.indexed_files),
            'model_name': self.model_name,
            'dimension': self.dimension
        }
    
    def save(self, save_path: str) -> None:
        """
        Save the index to disk.

        Args:
            save_path: Directory path to save the index
        """
        save_dir = Path(save_path)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        self._ensure_index()
        assert self._index is not None
        _get_faiss().write_index(self._index, str(save_dir / 'faiss.index'))
        # Save documents and metadata
        data = {
            'documents': [
                {
                    'file_path': d.file_path,
                    'line_index': d.line_index,
                    'line_text': d.line_text,
                    'line_count': d.line_count
                }
                for d in self.documents
            ],
            'indexed_files': list(self.indexed_files),
            'file_metadata': self.file_metadata,
            'model_name': self.model_name,
            'dimension': self.dimension
        }
        
        with open(save_dir / 'metadata.pkl', 'wb') as f:
            pickle.dump(data, f)

    def load(self, save_path: str) -> None:
        """
        Load the index from disk.

        Args:
            save_path: Directory path containing the saved index
        """
        save_dir = Path(save_path)

        # Load FAISS index (already initialized by read_index)
        self._index = _get_faiss().read_index(str(save_dir / 'faiss.index'))

        # Load metadata
        with open(save_dir / 'metadata.pkl', 'rb') as f:
            data = pickle.load(f)
        
        self.documents = [
            DocumentLine(
                file_path=d['file_path'],
                line_index=d['line_index'],
                line_text=d['line_text'],
                line_count=d['line_count']
            )
            for d in data['documents']
        ]
        self.indexed_files = set(data['indexed_files'])
        self.file_metadata = data.get('file_metadata', {})
        self.model_name = data['model_name']
        self._dimension = data['dimension']
        # Reset model to trigger lazy loading
        self._model = None
        
    
    def clear(self) -> None:
        """Clear the index and all data."""
        self._init_index()
        self.documents = []
        self.indexed_files = set()
        self.file_metadata = {}
        self._model = None  # Reset model for lazy reload

