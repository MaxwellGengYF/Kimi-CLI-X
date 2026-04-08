"""Embedding utilities for skill_rag.

This module provides a simple hash-based embedding service that doesn't require
any external ML models. All embeddings are generated deterministically using
text hashing for consistent vector representations.
"""

import hashlib
import logging
from typing import List

logger = logging.getLogger(__name__)


class SimpleEmbedder:
    """Simple deterministic embedder using text hashing.
    
    This embedder generates embeddings using MD5 hashing of text chunks,
    providing consistent vector representations without requiring any
    external ML models or dependencies.
    
    Args:
        dimension: Embedding dimension (default: 384)
    """
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        logger.info(f"SimpleEmbedder initialized with dimension {dimension}")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate deterministic embeddings for texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        return [self._text_to_vector(text) for text in texts]
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text.
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        return self._text_to_vector(text)
    
    def _text_to_vector(self, text: str) -> List[float]:
        """Convert text to a deterministic vector using hashing.
        
        Args:
            text: Input text
            
        Returns:
            Normalized vector of specified dimension
        """
        if not text:
            return [0.0] * self.dimension
        
        # Initialize vector
        vector = [0.0] * self.dimension
        
        # Split text into chunks for hashing
        chunk_size = max(1, len(text) // 16)
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        # Generate hash-based features
        for i, chunk in enumerate(chunks):
            # Use MD5 for consistent hashing
            hash_bytes = hashlib.md5(chunk.encode('utf-8')).digest()
            
            # Distribute hash values across vector dimensions
            for j in range(self.dimension):
                # Use multiple bytes for better distribution
                byte_idx = (j * 2) % len(hash_bytes)
                value = hash_bytes[byte_idx] / 255.0  # Normalize to [0, 1]
                
                # Weight by position in text
                weight = 1.0 / (1 + i)
                vector[j] += value * weight
        
        # Normalize the vector
        magnitude = sum(x * x for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        return vector


# Backward compatibility alias
EmbeddingService = SimpleEmbedder
