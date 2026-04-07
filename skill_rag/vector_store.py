"""ChromaDB vector store implementation."""

from typing import List, Optional, Dict, Any
from pathlib import Path
import chromadb
from chromadb.config import Settings


class ChromaVectorStore:
    """Wrapper for ChromaDB vector database operations."""
    
    def __init__(
        self,
        collection_name: str = "documents",
        persist_directory: Optional[str] = None,
        embedding_dimension: int = 384
    ):
        """Initialize ChromaDB vector store.
        
        Args:
            collection_name: Name of the collection
            persist_directory: Directory to persist data (None for in-memory)
            embedding_dimension: Dimension of embedding vectors
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.embedding_dimension = embedding_dimension
        self._client: Optional[chromadb.Client] = None
        self._collection = None
    
    def _get_client(self) -> chromadb.Client:
        """Get or create ChromaDB client."""
        if self._client is None:
            if self.persist_directory:
                Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
            else:
                self._client = chromadb.EphemeralClient(
                    settings=Settings(anonymized_telemetry=False)
                )
        return self._client
    
    def _get_collection(self):
        """Get or create collection."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"dimension": self.embedding_dimension}
            )
        return self._collection
    
    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> None:
        """Add documents with embeddings to the store.
        
        Args:
            documents: List of document texts
            embeddings: List of embedding vectors
            metadatas: Optional list of metadata dicts
            ids: Optional list of document IDs (auto-generated if None)
        """
        if not documents:
            return
        
        collection = self._get_collection()
        
        # Generate IDs if not provided
        if ids is None:
            existing_count = collection.count()
            ids = [f"doc_{existing_count + i}" for i in range(len(documents))]
        
        # Add in batches to avoid memory issues
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            end_idx = min(i + batch_size, len(documents))
            collection.add(
                documents=documents[i:end_idx],
                embeddings=embeddings[i:end_idx],
                metadatas=metadatas[i:end_idx] if metadatas else None,
                ids=ids[i:end_idx]
            )
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query the store for similar documents.
        
        Args:
            query_embedding: Query vector
            n_results: Number of results to return
            filter_dict: Optional metadata filter
            
        Returns:
            Dict with keys: ids, documents, metadatas, distances
        """
        collection = self._get_collection()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_dict
        )
        
        return results
    
    def delete_collection(self) -> None:
        """Delete the entire collection."""
        if self._client is not None:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass
        self._collection = None
    
    def reset(self) -> None:
        """Reset the store (delete all documents)."""
        client = self._get_client()
        try:
            # Delete and recreate the collection
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        # Reset collection reference so it gets recreated on next use
        self._collection = None
    
    def count(self) -> int:
        """Get the number of documents in the store.
        
        Returns:
            Document count
        """
        collection = self._get_collection()
        return collection.count()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics.
        
        Returns:
            Dict with stats
        """
        return {
            "collection_name": self.collection_name,
            "document_count": self.count(),
            "embedding_dimension": self.embedding_dimension,
            "persist_directory": self.persist_directory
        }
