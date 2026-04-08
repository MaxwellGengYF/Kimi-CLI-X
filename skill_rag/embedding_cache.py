"""Embedding cache for deterministic embedders.

This module provides caching for embeddings to avoid recomputing
them on subsequent runs. Useful for large document collections.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class EmbedderProtocol(Protocol):
    """Protocol for embedders that can be cached."""
    
    dimension: int
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...
    
    def embed_query(self, text: str) -> List[float]:
        ...


class EmbeddingCache:
    """Simple file-based cache for embeddings.
    
    Uses content hashing to generate cache keys, ensuring that
    identical text always maps to the same embedding.
    
    Args:
        cache_dir: Directory to store cache files
        dimension: Embedding dimension for validation
    """
    
    def __init__(self, cache_dir: Path, dimension: int = 384):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self._cache_file = self.cache_dir / "embeddings.json"
        self._embeddings: Dict[str, List[float]] = {}
        self._load()
    
    def _load(self) -> None:
        """Load existing cache from disk."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._embeddings = data.get("embeddings", {})
                    cached_dim = data.get("dimension", 0)
                    if cached_dim != self.dimension:
                        logger.warning(
                            f"Cache dimension mismatch: {cached_dim} vs {self.dimension}. "
                            "Clearing cache."
                        )
                        self._embeddings = {}
                logger.info(f"Loaded {len(self._embeddings)} cached embeddings")
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}")
                self._embeddings = {}
    
    def _save(self) -> None:
        """Save cache to disk."""
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "embeddings": self._embeddings,
                    "dimension": self.dimension,
                    "version": "1.0"
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")
    
    def _get_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get cached embedding for text.
        
        Args:
            text: Text to look up
            
        Returns:
            Cached embedding or None
        """
        key = self._get_key(text)
        return self._embeddings.get(key)
    
    def set(self, text: str, embedding: List[float]) -> None:
        """Cache embedding for text.
        
        Args:
            text: Original text
            embedding: Computed embedding
        """
        key = self._get_key(text)
        self._embeddings[key] = embedding
        # Save periodically (every 100 new entries)
        if len(self._embeddings) % 100 == 0:
            self._save()
    
    def get_batch(self, texts: List[str]) -> tuple[List[Optional[List[float]]], List[int]]:
        """Get cached embeddings for a batch of texts.
        
        Args:
            texts: List of texts to look up
            
        Returns:
            Tuple of (embeddings, missing_indices)
            - embeddings: List of embeddings (None for cache misses)
            - missing_indices: Indices of texts not in cache
        """
        embeddings = []
        missing_indices = []
        
        for i, text in enumerate(texts):
            cached = self.get(text)
            embeddings.append(cached)
            if cached is None:
                missing_indices.append(i)
        
        return embeddings, missing_indices
    
    def set_batch(self, texts: List[str], embeddings: List[List[float]]) -> None:
        """Cache embeddings for a batch of texts.
        
        Args:
            texts: Original texts
            embeddings: Computed embeddings
        """
        for text, embedding in zip(texts, embeddings):
            self.set(text, embedding)
        self._save()
    
    def clear(self) -> None:
        """Clear all cached embeddings."""
        self._embeddings.clear()
        if self._cache_file.exists():
            self._cache_file.unlink()
        logger.info("Embedding cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cached_count": len(self._embeddings),
            "dimension": self.dimension,
            "cache_file": str(self._cache_file)
        }


class CachedEmbedder:
    """Wrapper that adds caching to any embedder.
    
    Args:
        embedder: Base embedder to wrap
        cache_dir: Directory for cache files
        enabled: Whether caching is enabled
    """
    
    def __init__(
        self,
        embedder: EmbedderProtocol,
        cache_dir: Optional[Path] = None,
        enabled: bool = True
    ):
        self.embedder = embedder
        self.dimension = embedder.dimension
        self._enabled = enabled
        
        if enabled:
            cache_path = cache_dir or Path(".embedding_cache")
            self.cache = EmbeddingCache(cache_path, dimension=embedder.dimension)
        else:
            self.cache = None
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings with caching.
        
        Args:
            texts: Texts to embed
            
        Returns:
            List of embeddings
        """
        if not self._enabled or self.cache is None:
            return self.embedder.embed(texts)
        
        # Check cache
        embeddings, missing_indices = self.cache.get_batch(texts)
        
        # Compute missing embeddings
        if missing_indices:
            missing_texts = [texts[i] for i in missing_indices]
            missing_embeddings = self.embedder.embed(missing_texts)
            
            # Update cache
            self.cache.set_batch(missing_texts, missing_embeddings)
            
            # Fill in missing embeddings
            for idx, emb in zip(missing_indices, missing_embeddings):
                embeddings[idx] = emb
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for query with caching.
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector
        """
        if not self._enabled or self.cache is None:
            return self.embedder.embed_query(text)
        
        # Check cache
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        
        # Compute and cache
        embedding = self.embedder.embed_query(text)
        self.cache.set(text, embedding)
        return embedding


def create_cached_embedder(
    embedder: EmbedderProtocol,
    cache_dir: Optional[str] = None,
    enabled: bool = True
) -> CachedEmbedder:
    """Create a cached embedder.
    
    Args:
        embedder: Base embedder to wrap
        cache_dir: Directory for cache (None for default)
        enabled: Whether to enable caching
        
    Returns:
        CachedEmbedder instance
    """
    cache_path = Path(cache_dir) if cache_dir else None
    return CachedEmbedder(embedder, cache_dir=cache_path, enabled=enabled)
