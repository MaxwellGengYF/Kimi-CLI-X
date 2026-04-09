"""Embedding cache for deterministic embedders.

This module provides caching for embeddings to avoid recomputing
them on subsequent runs. Uses binary format with float16 quantization
for efficient storage.
"""

import hashlib
import json
import logging
import struct
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class EmbedderProtocol(Protocol):
    """Protocol for embedders that can be cached."""
    
    dimension: int
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...
    
    def embed_query(self, text: str) -> List[float]:
        ...


class CompressedEmbeddingCache:
    """Memory-efficient embedding cache with binary storage and float16 quantization.
    
    Uses numpy binary format (.npz) for efficient storage and supports
    float16 quantization to reduce memory usage by 50%.
    
    Args:
        cache_dir: Directory to store cache files
        dimension: Embedding dimension for validation
        max_memory_entries: Maximum number of entries to keep in memory (LRU eviction)
        quantization: Whether to use float16 quantization (saves 50% space)
    """
    
    CACHE_VERSION = 2  # Version for format compatibility
    
    def __init__(
        self,
        cache_dir: Path,
        dimension: int = 384,
        max_memory_entries: int = 10000,
        quantization: bool = True
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self.max_memory_entries = max_memory_entries
        self.quantization = quantization
        
        # Use OrderedDict for LRU tracking
        self._embeddings: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_file = self.cache_dir / "embeddings.npz"
        self._metadata_file = self.cache_dir / "metadata.json"
        
        self._load()
    
    def _load(self) -> None:
        """Load existing cache from disk."""
        if not self._cache_file.exists():
            logger.info("No existing cache found")
            return
        
        try:
            # Load metadata first
            metadata = {}
            if self._metadata_file.exists():
                with open(self._metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            
            # Check version compatibility
            cache_version = metadata.get("version", 1)
            if cache_version != self.CACHE_VERSION:
                logger.warning(
                    f"Cache version mismatch: {cache_version} vs {self.CACHE_VERSION}. "
                    "Clearing cache."
                )
                self._embeddings.clear()
                return
            
            # Check dimension compatibility
            cached_dim = metadata.get("dimension", 0)
            if cached_dim != self.dimension:
                logger.warning(
                    f"Cache dimension mismatch: {cached_dim} vs {self.dimension}. "
                    "Clearing cache."
                )
                self._embeddings.clear()
                return
            
            # Load embeddings from npz file
            loaded = np.load(self._cache_file, allow_pickle=False)
            quantization_mode = metadata.get("quantization", False)
            
            for key in loaded.files:
                embedding = loaded[key]
                # Dequantize if needed
                if quantization_mode and embedding.dtype == np.float16:
                    embedding = embedding.astype(np.float32)
                self._embeddings[key] = embedding
            
            logger.info(
                f"Loaded {len(self._embeddings)} cached embeddings "
                f"({'with' if quantization_mode else 'without'} quantization)"
            )
            
        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")
            self._embeddings.clear()
    
    def _save(self) -> None:
        """Save cache to disk using binary format."""
        try:
            # Prepare arrays for saving
            arrays = {}
            for key, embedding in self._embeddings.items():
                # Sanitize key for numpy (replace invalid chars)
                safe_key = key.replace('/', '_').replace('\\', '_')
                # Quantize to float16 if enabled
                if self.quantization and embedding.dtype == np.float32:
                    arrays[safe_key] = embedding.astype(np.float16)
                else:
                    arrays[safe_key] = embedding
            
            # Save embeddings
            if arrays:
                np.savez_compressed(self._cache_file, **arrays)
            else:
                # Create empty npz file
                np.savez_compressed(self._cache_file, __empty=np.array([]))
            
            # Save metadata
            metadata = {
                "version": self.CACHE_VERSION,
                "dimension": self.dimension,
                "quantization": self.quantization,
                "count": len(self._embeddings)
            }
            with open(self._metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f)
            
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")
    
    def _get_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _ensure_lru_space(self) -> None:
        """Ensure we have space in memory cache using LRU eviction."""
        while len(self._embeddings) >= self.max_memory_entries:
            # Remove oldest item (first in OrderedDict)
            oldest_key = next(iter(self._embeddings))
            del self._embeddings[oldest_key]
            logger.debug(f"LRU evicted embedding: {oldest_key}")
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get cached embedding for text.
        
        Args:
            text: Text to look up
            
        Returns:
            Cached embedding or None
        """
        key = self._get_key(text)
        if key in self._embeddings:
            # Move to end (most recently used)
            embedding = self._embeddings.pop(key)
            self._embeddings[key] = embedding
            return embedding.tolist()
        return None
    
    def set(self, text: str, embedding: List[float]) -> None:
        """Cache embedding for text.
        
        Args:
            text: Original text
            embedding: Computed embedding
        """
        key = self._get_key(text)
        
        # Ensure LRU space
        if key not in self._embeddings:
            self._ensure_lru_space()
        
        # Store as numpy array (float32 for memory efficiency)
        self._embeddings[key] = np.array(embedding, dtype=np.float32)
        
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
        if self._metadata_file.exists():
            self._metadata_file.unlink()
        logger.info("Embedding cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        memory_mb = sum(
            emb.nbytes for emb in self._embeddings.values()
        ) / (1024 * 1024)
        
        return {
            "cached_count": len(self._embeddings),
            "dimension": self.dimension,
            "quantization": self.quantization,
            "memory_usage_mb": round(memory_mb, 2),
            "max_memory_entries": self.max_memory_entries,
            "cache_file": str(self._cache_file),
            "version": self.CACHE_VERSION
        }


# Backwards compatibility - alias for existing code
EmbeddingCache = CompressedEmbeddingCache


class CachedEmbedder:
    """Wrapper that adds caching to any embedder.
    
    Args:
        embedder: Base embedder to wrap
        cache_dir: Directory for cache files
        enabled: Whether caching is enabled
        max_memory_entries: Maximum entries in memory cache
        quantization: Whether to use float16 quantization
    """
    
    def __init__(
        self,
        embedder: EmbedderProtocol,
        cache_dir: Optional[Path] = None,
        enabled: bool = True,
        max_memory_entries: int = 10000,
        quantization: bool = True
    ):
        self.embedder = embedder
        self.dimension = embedder.dimension
        self._enabled = enabled
        
        if enabled:
            cache_path = cache_dir or Path(".embedding_cache")
            self.cache = CompressedEmbeddingCache(
                cache_path,
                dimension=embedder.dimension,
                max_memory_entries=max_memory_entries,
                quantization=quantization
            )
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
    enabled: bool = True,
    max_memory_entries: int = 10000,
    quantization: bool = True
) -> CachedEmbedder:
    """Create a cached embedder.
    
    Args:
        embedder: Base embedder to wrap
        cache_dir: Directory for cache (None for default)
        enabled: Whether to enable caching
        max_memory_entries: Maximum entries to keep in memory
        quantization: Whether to use float16 quantization on disk
        
    Returns:
        CachedEmbedder instance
    """
    cache_path = Path(cache_dir) if cache_dir else None
    return CachedEmbedder(
        embedder,
        cache_dir=cache_path,
        enabled=enabled,
        max_memory_entries=max_memory_entries,
        quantization=quantization
    )
