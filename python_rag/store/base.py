"""Base interface for document stores."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Iterator


class Document:
    """Represents a document in the store."""
    
    def __init__(
        self,
        id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None
    ):
        self.id = id
        self.content = content
        self.metadata = metadata or {}
        self.embedding = embedding
    
    def __repr__(self) -> str:
        return f"Document(id={self.id}, content={self.content[:50]}...)"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Document to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "embedding": self.embedding
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        """Create Document from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            embedding=data.get("embedding")
        )


class BaseDocumentStore(ABC):
    """Abstract base class for document stores."""
    
    @abstractmethod
    def add(self, documents: List[Document]) -> None:
        """Add documents to the store."""
        pass
    
    @abstractmethod
    def get(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID."""
        pass
    
    @abstractmethod
    def delete(self, doc_ids: List[str]) -> None:
        """Delete documents by IDs."""
        pass
    
    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """Search documents by vector similarity."""
        pass
    
    @abstractmethod
    def get_all(self) -> Iterator[Document]:
        """Get all documents from the store."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Return the number of documents in the store."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear all documents from the store."""
        pass
