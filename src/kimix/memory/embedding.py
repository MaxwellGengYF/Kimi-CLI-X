"""Embedding vector provider."""

import hashlib
from typing import Dict, List

import numpy as np


class EmbeddingProvider:
    """Embedding vector provider (replaceable with OpenAI, local models, etc.)."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        # Production: use real models; here using simulation
        self._cache: Dict[str, List[float]] = {}

    def embed(self, text: str) -> List[float]:
        """Generate text vector embedding."""
        if text in self._cache:
            return self._cache[text]

        # Simulated embedding: hash-based deterministic vector
        # Production replacement: openai.Embedding.create() or sentence-transformers
        hash_val = hashlib.md5(text.encode()).hexdigest()
        np.random.seed(int(hash_val[:8], 16))
        vec = np.random.randn(self.dim).astype(np.float32)
        vec = vec / np.linalg.norm(vec)  # Normalize

        self._cache[text] = vec.tolist()
        return self._cache[text]

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity."""
        v1, v2 = np.array(vec1), np.array(vec2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm)
