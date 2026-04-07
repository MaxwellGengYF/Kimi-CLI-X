"""Base interface for embedding models."""

from abc import ABC, abstractmethod
from typing import List, Union


class BaseEmbeddingModel(ABC):
    """Abstract base class for embedding models."""
    
    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        pass
    
    @abstractmethod
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """
        Embed text(s) into vector(s).
        
        Args:
            texts: Single text or list of texts to embed
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        pass
    
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
