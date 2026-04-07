"""Sentence-Transformers embedding model implementation."""

from typing import List, Union, Optional
import numpy as np

from .base import BaseEmbeddingModel


class SentenceTransformerEmbedding(BaseEmbeddingModel):
    """
    Local embedding model using sentence-transformers.
    
    Default model: 'sentence-transformers/all-MiniLM-L6-v2'
    - Embedding dimension: 384
    - Max sequence length: 256
    - Optimized for semantic similarity
    """
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
        batch_size: int = 32,
        cache_folder: Optional[str] = None,
        local_files_only: bool = True,
    ):
        """
        Initialize sentence-transformers embedding model.
        
        Args:
            model_name: HuggingFace model name or local path
            device: Device to run on ('cpu', 'cuda', 'cuda:0', etc.)
            normalize_embeddings: Whether to L2-normalize embeddings
            batch_size: Batch size for encoding
            cache_folder: Cache directory for models
            local_files_only: If True, only load models from local cache (offline mode)
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required. "
                "Install with: pip install sentence-transformers"
            )
        
        self.model_name = model_name
        self.device = device or ("cuda" if self._is_cuda_available() else "cpu")
        self.normalize_embeddings = normalize_embeddings
        self.batch_size = batch_size
        self.cache_folder = cache_folder
        self.local_files_only = local_files_only
        
        # Load model
        self._model = SentenceTransformer(
            model_name, 
            device=self.device,
            cache_folder=cache_folder,
            local_files_only=local_files_only,
        )
        self._embedding_dim = self._model.get_sentence_embedding_dimension()
    
    @staticmethod
    def _is_cuda_available() -> bool:
        """Check if CUDA is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        return self._embedding_dim
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """
        Embed text(s) into vector(s).
        
        Args:
            texts: Single text or list of texts to embed
            
        Returns:
            List of embedding vectors
        """
        # Ensure list input
        if isinstance(texts, str):
            texts = [texts]
        
        # Filter out empty strings
        texts = [t if t.strip() else " " for t in texts]
        
        # Generate embeddings
        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        # Convert to list of lists
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query text.
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        result = self.embed(text)
        return result[0]
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents.
        
        Args:
            texts: List of document texts
            
        Returns:
            List of embedding vectors
        """
        return self.embed(texts)


class MiniLMEmbedding(SentenceTransformerEmbedding):
    """
    Convenience class for all-MiniLM-L6-v2 model.
    
    Lightweight model suitable for most use cases:
    - 384 dimensions
    - Fast inference
    - Good balance of quality and speed
    """
    
    def __init__(
        self,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
        batch_size: int = 32,
        cache_folder: Optional[str] = None,
        local_files_only: bool = True,
    ):
        super().__init__(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            device=device,
            normalize_embeddings=normalize_embeddings,
            batch_size=batch_size,
            cache_folder=cache_folder,
            local_files_only=local_files_only,
        )


class MPNetEmbedding(SentenceTransformerEmbedding):
    """
    Convenience class for all-mpnet-base-v2 model.
    
    Higher quality model:
    - 768 dimensions
    - Better semantic similarity
    - Slower than MiniLM
    """
    
    def __init__(
        self,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
        batch_size: int = 32,
        cache_folder: Optional[str] = None,
        local_files_only: bool = True,
    ):
        super().__init__(
            model_name="sentence-transformers/all-mpnet-base-v2",
            device=device,
            normalize_embeddings=normalize_embeddings,
            batch_size=batch_size,
            cache_folder=cache_folder,
            local_files_only=local_files_only,
        )
