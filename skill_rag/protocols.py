"""Protocol definitions for dependency injection.

This module defines protocols (structural subtypes) for the main components
of the RAG pipeline, enabling dependency injection and easier testing.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Protocol for embedding generators."""
    
    dimension: int
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors, one per input text
        """
        ...
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text.
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector storage backends."""
    
    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """Add documents with embeddings to the store.
        
        Args:
            documents: List of document texts
            embeddings: List of embedding vectors
            metadatas: Optional list of metadata dicts
            ids: Optional list of document IDs
            
        Returns:
            List of document IDs
        """
        ...
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        min_similarity: Optional[float] = None
    ) -> Dict[str, Any]:
        """Query the store for similar documents.
        
        Args:
            query_embedding: Query vector
            n_results: Number of results to return
            filter_dict: Optional metadata filter
            min_similarity: Optional minimum similarity threshold
            
        Returns:
            Dict with keys: ids, documents, metadatas, distances
        """
        ...
    
    def delete_by_id(self, doc_id: str) -> bool:
        """Delete a document by ID.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            True if deleted successfully
        """
        ...
    
    def delete_by_ids(self, doc_ids: List[str]) -> bool:
        """Delete multiple documents by ID.
        
        Args:
            doc_ids: List of document IDs to delete
            
        Returns:
            True if deleted successfully
        """
        ...
    
    def count(self) -> int:
        """Get the number of documents in the store."""
        ...
    
    def reset(self) -> None:
        """Reset the store (delete all documents)."""
        ...


@runtime_checkable
class DocumentLoader(Protocol):
    """Protocol for document loaders."""
    
    def load_file(self, file_path: Any) -> List[Any]:
        """Load a file and return documents.
        
        Args:
            file_path: Path to the file to load
            
        Returns:
            List of document objects
        """
        ...
    
    def load(self, source: Any) -> List[Any]:
        """Load from a source (file or directory).
        
        Args:
            source: Path or other source identifier
            
        Returns:
            List of document objects
        """
        ...


@runtime_checkable
class Document(Protocol):
    """Protocol for document objects."""
    
    content: str
    source: str
    metadata: Dict[str, Any]
