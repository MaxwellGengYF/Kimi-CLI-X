"""Embedding cache with diskcache integration for deduplication.

This module provides caching for text embeddings to avoid recomputing
embeddings for the same text multiple times, significantly improving
performance for repeated queries and indexed documents.
"""

import hashlib
import json
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np

from skill_rag.config import get_config, EmbeddingConfig

try:
    import diskcache
    DISKCACHE_AVAILABLE = True
except ImportError:
    DISKCACHE_AVAILABLE = False


class EmbeddingCache:
    """Cache for text embeddings using diskcache.
    
    Provides persistent caching of embeddings with automatic invalidation
    based on model and configuration changes.
    
    Example:
        >>> cache = EmbeddingCache()
        >>> embedding = cache.get_or_compute("text", embed_fn)
        >>> cache.close()
    """
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        enabled: bool = True,
        max_size_gb: float = 1.0,
        config: Optional[EmbeddingConfig] = None
    ):
        """Initialize embedding cache.
        
        Args:
            cache_dir: Directory for cache storage. Uses config default if None.
            enabled: Whether caching is enabled
            max_size_gb: Maximum cache size in GB
            config: Embedding configuration for cache versioning
        """
        self.enabled = enabled and DISKCACHE_AVAILABLE
        self.config = config or get_config().embedding
        
        if not self.enabled:
            self._cache = None
            return
            
        if cache_dir is None:
            cache_dir = Path(self.config.cache_dir)
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize diskcache with size limit
        size_limit = int(max_size_gb * 1024 * 1024 * 1024)  # Convert GB to bytes
        self._cache = diskcache.Cache(
            directory=str(self.cache_dir),
            size_limit=size_limit,
            eviction_policy='least-recently-used'
        )
        
        # Cache version for invalidation
        self._version = self._compute_version()
    
    def _compute_version(self) -> str:
        """Compute cache version based on model and config.
        
        Returns:
            Version string that changes when model/config changes
        """
        version_data = {
            'model_name': self.config.model_name,
            'normalize': self.config.normalize,
            'cache_format': 'v1'  # Bump when cache format changes
        }
        return hashlib.md5(
            json.dumps(version_data, sort_keys=True).encode()
        ).hexdigest()[:8]
    
    def _make_key(self, text: str) -> str:
        """Create cache key for text.
        
        Args:
            text: Input text
            
        Returns:
            Cache key string
        """
        # Include version in key for automatic invalidation
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        return f"{self._version}:{text_hash}"
    
    def get(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache.
        
        Args:
            text: Input text
            
        Returns:
            Cached embedding or None if not found
        """
        if not self.enabled or self._cache is None:
            return None
        
        key = self._make_key(text)
        try:
            data = self._cache.get(key)
            if data is not None:
                return np.frombuffer(data, dtype=np.float32)
        except Exception:
            pass  # Cache miss or error
        
        return None
    
    def set(self, text: str, embedding: np.ndarray) -> None:
        """Store embedding in cache.
        
        Args:
            text: Input text
            embedding: Embedding vector
        """
        if not self.enabled or self._cache is None:
            return
        
        key = self._make_key(text)
        try:
            # Store as bytes for efficiency
            self._cache.set(key, embedding.astype(np.float32).tobytes())
        except Exception:
            pass  # Cache error, ignore
    
    def get_or_compute(
        self,
        text: str,
        compute_fn: Callable[[str], np.ndarray]
    ) -> np.ndarray:
        """Get embedding from cache or compute and store.
        
        Args:
            text: Input text
            compute_fn: Function to compute embedding if not cached
            
        Returns:
            Embedding vector
        """
        # Try cache first
        cached = self.get(text)
        if cached is not None:
            return cached
        
        # Compute embedding
        embedding = compute_fn(text)
        
        # Store in cache
        self.set(text, embedding)
        
        return embedding
    
    def get_batch(
        self,
        texts: List[str],
        compute_fn: Callable[[List[str]], List[np.ndarray]]
    ) -> List[np.ndarray]:
        """Get embeddings for batch with caching.
        
        Args:
            texts: List of input texts
            compute_fn: Function to compute embeddings for uncached texts
            
        Returns:
            List of embedding vectors (same order as input)
        """
        if not self.enabled:
            # Ensure consistent return type as list of numpy arrays
            result = compute_fn(texts)
            return [np.asarray(emb) for emb in result]
        
        # Check cache for each text
        results = []
        missing_indices = []
        missing_texts = []
        
        for i, text in enumerate(texts):
            cached = self.get(text)
            if cached is not None:
                results.append((i, cached))
            else:
                missing_indices.append(i)
                missing_texts.append(text)
                results.append((i, None))  # Placeholder
        
        # Compute missing embeddings
        if missing_texts:
            computed = compute_fn(missing_texts)
            for idx, text, embedding in zip(missing_indices, missing_texts, computed):
                # Convert to numpy array for consistency
                emb_array = np.asarray(embedding)
                self.set(text, emb_array)
                results[idx] = (idx, emb_array)
        
        # Return in original order
        return [emb for _, emb in sorted(results, key=lambda x: x[0])]
    
    def clear(self) -> None:
        """Clear all cached embeddings."""
        if self._cache is not None:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.enabled or self._cache is None:
            return {
                'enabled': False,
                'size': 0,
                'hits': 0,
                'misses': 0
            }
        
        # diskcache.stats() returns tuple (hits, misses)
        hits, misses = self._cache.stats()
        total = hits + misses
        return {
            'enabled': True,
            'directory': str(self.cache_dir),
            'version': self._version,
            'size': len(self._cache),
            'hits': hits,
            'misses': misses,
            'hit_rate': hits / max(total, 1)
        }
    
    def close(self) -> None:
        """Close cache and release resources."""
        if self._cache is not None:
            self._cache.close()
            self._cache = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


def cached_embedder(cache: Optional[EmbeddingCache] = None):
    """Decorator to add caching to embedder methods.
    
    Args:
        cache: EmbeddingCache instance. Creates default if None.
        
    Returns:
        Decorator function
    """
    def decorator(compute_fn):
        @wraps(compute_fn)
        def wrapper(texts, *args, **kwargs):
            # Create cache if not provided
            nonlocal cache
            if cache is None:
                cache = EmbeddingCache()
            
            # Single text
            if isinstance(texts, str):
                return cache.get_or_compute(texts, lambda t: compute_fn([t], *args, **kwargs)[0])
            
            # Batch of texts
            return cache.get_batch(texts, lambda ts: compute_fn(ts, *args, **kwargs))
        
        return wrapper
    return decorator


class CachedEmbedder:
    """Wrapper that adds caching to any embedder.
    
    Example:
        >>> from skill_rag.embedders import SentenceTransformerEmbedder
        >>> embedder = SentenceTransformerEmbedder()
        >>> cached = CachedEmbedder(embedder)
        >>> embedding = cached.embed("text")  # Cached on second call
    """
    
    def __init__(
        self,
        embedder: Any,
        cache: Optional[EmbeddingCache] = None,
        cache_dir: Optional[Path] = None,
        enabled: bool = True
    ):
        """Initialize cached embedder wrapper.
        
        Args:
            embedder: Base embedder to wrap
            cache: Existing EmbeddingCache instance
            cache_dir: Directory for cache (creates new if cache not provided)
            enabled: Whether caching is enabled
        """
        self.embedder = embedder
        
        if cache is not None:
            self.cache = cache
        elif enabled:
            self.cache = EmbeddingCache(cache_dir=cache_dir, enabled=enabled)
        else:
            self.cache = EmbeddingCache(enabled=False)
        
        # Expose underlying embedder's dimension attribute
        self.dimension = getattr(embedder, 'dimension', 384)
    
    def embed(self, texts: Union[str, List[str]], batch_size: int = 32) -> List[List[float]]:
        """Embed text(s) with caching.
        
        Args:
            texts: Single text or list of texts
            batch_size: Batch size (for API compatibility)
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if isinstance(texts, str):
            # Single text - treat as batch of 1
            texts = [texts]
        
        # Process batch - check cache for all texts first
        results = [None] * len(texts)
        missing_indices = []
        missing_texts = []
        
        for i, text in enumerate(texts):
            cached = self.cache.get(text)
            if cached is not None:
                # Convert numpy array to list
                results[i] = cached.tolist()
            else:
                missing_indices.append(i)
                missing_texts.append(text)
        
        # Compute missing embeddings in batch for efficiency
        if missing_texts:
            computed = self.embedder.embed(missing_texts, batch_size)
            for idx, text, emb in zip(missing_indices, missing_texts, computed):
                # Ensure embedding is a list
                if isinstance(emb, np.ndarray):
                    emb = emb.tolist()
                # Store in cache (cache expects numpy array)
                self.cache.set(text, np.asarray(emb))
                results[idx] = emb
        
        return results
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed batch of texts with caching.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        # Use the embed method which handles caching
        return self.embed(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a query text with caching.
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector as list of floats
        """
        # Queries can use the same cache as documents
        result = self.embed(text)
        # result is List[List[float]], return first element
        return result[0] if result else []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self.cache.clear()
    
    def close(self) -> None:
        """Close cache and release resources."""
        self.cache.close()
