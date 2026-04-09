"""ChromaDB vector store implementation with full CRUD support."""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
import threading
import chromadb
from chromadb.config import Settings


logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Wrapper for ChromaDB vector database operations with full CRUD support."""
    
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
        self._lock = threading.RLock()  # Thread-safe lock for concurrent operations
    
    def _get_client(self) -> chromadb.Client:
        """Get or create ChromaDB client."""
        if self._client is None:
            with self._lock:
                # Double-check after acquiring lock
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
            with self._lock:
                # Double-check after acquiring lock
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
    ) -> List[str]:
        """Add documents with embeddings to the store.
        
        Args:
            documents: List of document texts
            embeddings: List of embedding vectors
            metadatas: Optional list of metadata dicts
            ids: Optional list of document IDs (auto-generated if None)
            
        Returns:
            List of document IDs
        """
        if not documents:
            return []
        
        with self._lock:
            collection = self._get_collection()
            
            # Generate IDs if not provided
            if ids is None:
                existing_count = collection.count()
                ids = [f"doc_{existing_count + i}" for i in range(len(documents))]
            
            # Add in batches to avoid memory issues
            batch_size = 1000
            for i in range(0, len(documents), batch_size):
                end_idx = min(i + batch_size, len(documents))
                collection.add(
                    documents=documents[i:end_idx],
                    embeddings=embeddings[i:end_idx],
                    metadatas=metadatas[i:end_idx] if metadatas else None,
                    ids=ids[i:end_idx]
                )
            
            return ids
    
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document dict with keys: id, document, metadata, embedding
            or None if not found
        """
        collection = self._get_collection()
        try:
            result = collection.get(
                ids=[doc_id],
                include=["documents", "metadatas", "embeddings"]
            )
            if result["ids"] and len(result["ids"]) > 0:
                return {
                    "id": result["ids"][0],
                    "document": result["documents"][0] if result.get("documents") else None,
                    "metadata": result["metadatas"][0] if result.get("metadatas") else None,
                    "embedding": result["embeddings"][0] if result.get("embeddings") is not None and len(result["embeddings"]) > 0 else None
                }
        except Exception:
            pass
        return None
    
    def get_documents(self, doc_ids: List[str]) -> List[Dict[str, Any]]:
        """Get multiple documents by ID.
        
        Args:
            doc_ids: List of document IDs
            
        Returns:
            List of document dicts
        """
        if not doc_ids:
            return []
        
        collection = self._get_collection()
        try:
            result = collection.get(
                ids=doc_ids,
                include=["documents", "metadatas", "embeddings"]
            )
            documents = []
            for i, doc_id in enumerate(result["ids"]):
                documents.append({
                    "id": doc_id,
                    "document": result["documents"][i] if result.get("documents") else None,
                    "metadata": result["metadatas"][i] if result.get("metadatas") else None,
                    "embedding": result["embeddings"][i] if result.get("embeddings") is not None and len(result["embeddings"]) > i else None
                })
            return documents
        except Exception:
            return []
    
    def update_document(
        self,
        id: str,
        document: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update a document by ID.
        
        Args:
            id: Document ID
            document: New document text (optional)
            embedding: New embedding vector (optional)
            metadata: New metadata dict (optional, merges with existing)
            
        Returns:
            True if updated successfully, False otherwise
        """
        with self._lock:
            collection = self._get_collection()
            try:
                # Check if document exists
                existing = self.get_document(id)
                if existing is None:
                    return False
                
                # Build update parameters
                update_params = {"ids": [id]}
                if document is not None:
                    update_params["documents"] = [document]
                if embedding is not None:
                    update_params["embeddings"] = [embedding]
                if metadata is not None:
                    # Merge with existing metadata
                    merged_metadata = {**(existing.get("metadata") or {}), **metadata}
                    update_params["metadatas"] = [merged_metadata]
                
                collection.update(**update_params)
                return True
            except Exception as e:
                logger.error(f"Error updating document {id}: {e}")
                return False
    
    def upsert_document(
        self,
        id: str,
        document: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Insert or update a document.
        
        Args:
            id: Document ID
            document: Document text
            embedding: Embedding vector
            metadata: Metadata dict
            
        Returns:
            True if successful
        """
        with self._lock:
            collection = self._get_collection()
            try:
                collection.upsert(
                    ids=[id],
                    documents=[document],
                    embeddings=[embedding],
                    metadatas=[metadata] if metadata else None
                )
                return True
            except Exception as e:
                logger.error(f"Error upserting document {id}: {e}")
                return False
    
    def delete_by_id(self, doc_id: str) -> bool:
        """Delete a document by ID.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        return self.delete_by_ids([doc_id])
    
    def delete_by_ids(self, doc_ids: List[str]) -> bool:
        """Delete multiple documents by ID.
        
        Args:
            doc_ids: List of document IDs to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        if not doc_ids:
            return True
        
        with self._lock:
            collection = self._get_collection()
            try:
                collection.delete(ids=doc_ids)
                return True
            except Exception as e:
                logger.error(f"Error deleting documents: {e}")
                return False
    
    def delete_by_filter(self, filter_dict: Dict[str, Any]) -> int:
        """Delete documents matching a metadata filter.
        
        Args:
            filter_dict: ChromaDB where filter dict
            
        Returns:
            Number of documents deleted
        """
        with self._lock:
            collection = self._get_collection()
            try:
                # First get matching documents to count them
                results = collection.get(where=filter_dict)
                count = len(results["ids"]) if results["ids"] else 0
                
                # Delete matching documents
                collection.delete(where=filter_dict)
                return count
            except Exception as e:
                logger.error(f"Error deleting by filter: {e}")
                return 0
    
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
            min_similarity: Optional minimum similarity threshold (0-1, cosine similarity)
            
        Returns:
            Dict with keys: ids, documents, metadatas, distances
        """
        collection = self._get_collection()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_dict,
            include=["documents", "metadatas", "distances"]
        )
        
        # Apply similarity threshold if specified
        if min_similarity is not None and results["distances"]:
            # Convert distance to similarity (cosine distance -> cosine similarity)
            filtered_ids = []
            filtered_docs = []
            filtered_metas = []
            filtered_distances = []
            
            for i, distance in enumerate(results["distances"][0]):
                similarity = 1.0 - distance  # Convert distance to similarity
                if similarity >= min_similarity:
                    filtered_ids.append(results["ids"][0][i])
                    filtered_docs.append(results["documents"][0][i])
                    filtered_metas.append(results["metadatas"][0][i])
                    filtered_distances.append(distance)
            
            results = {
                "ids": [filtered_ids],
                "documents": [filtered_docs],
                "metadatas": [filtered_metas],
                "distances": [filtered_distances]
            }
        
        return results
    
    def get_by_metadata(
        self,
        filter_dict: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get documents by metadata filter.
        
        Args:
            filter_dict: ChromaDB where filter dict
            limit: Maximum number of documents to return
            
        Returns:
            List of document dicts
        """
        collection = self._get_collection()
        try:
            result = collection.get(
                where=filter_dict,
                limit=limit,
                include=["documents", "metadatas"]
            )
            documents = []
            for i, doc_id in enumerate(result["ids"]):
                documents.append({
                    "id": doc_id,
                    "document": result["documents"][i] if result["documents"] else None,
                    "metadata": result["metadatas"][i] if result["metadatas"] else None
                })
            return documents
        except Exception as e:
            logger.error(f"Error getting by metadata: {e}")
            return []
    
    def delete_collection(self) -> None:
        """Delete the entire collection."""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.delete_collection(self.collection_name)
                except Exception:
                    pass
            self._collection = None
    
    def reset(self) -> None:
        """Reset the store (delete all documents)."""
        with self._lock:
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
