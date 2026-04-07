"""ChromaDB implementation of document store for offline vector storage."""

import os
from typing import List, Dict, Any, Optional, Iterator
import chromadb
from chromadb.config import Settings
from chromadb.api.models.Collection import Collection

from .base import BaseDocumentStore, Document


class ChromaDocumentStore(BaseDocumentStore):
    """
    ChromaDB-based document store for offline vector storage.
    
    Supports persistent storage on disk for offline usage.
    """
    
    def __init__(
        self,
        collection_name: str = "documents",
        persist_directory: Optional[str] = None,
        embedding_function: Optional[Any] = None,
        distance_metric: str = "cosine"
    ):
        """
        Initialize ChromaDB document store.
        
        Args:
            collection_name: Name of the collection to use
            persist_directory: Directory to persist data (for offline storage)
            embedding_function: Optional custom embedding function
            distance_metric: Distance metric for similarity search (cosine, l2, ip)
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.embedding_function = embedding_function
        self.distance_metric = distance_metric
        
        # Initialize ChromaDB client
        if persist_directory:
            os.makedirs(persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        else:
            # In-memory client (not persistent)
            self.client = chromadb.EphemeralClient(
                settings=Settings(anonymized_telemetry=False)
            )
        
        # Get or create collection
        self.collection: Collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": distance_metric}
        )
    
    def add(self, documents: List[Document]) -> None:
        """
        Add documents to the store.
        
        Args:
            documents: List of Document objects to add
        """
        if not documents:
            return
        
        ids = [doc.id for doc in documents]
        contents = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        embeddings = [doc.embedding for doc in documents if doc.embedding is not None]
        
        # Filter out documents with None embeddings if any exist
        if len(embeddings) == len(documents):
            self.collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas,
                embeddings=embeddings
            )
        else:
            # Let ChromaDB compute embeddings
            self.collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas
            )
    
    def get(self, doc_id: str) -> Optional[Document]:
        """
        Get a document by ID.
        
        Args:
            doc_id: Document ID to retrieve
            
        Returns:
            Document if found, None otherwise
        """
        try:
            result = self.collection.get(ids=[doc_id])
            if result["ids"]:
                return Document(
                    id=result["ids"][0],
                    content=result["documents"][0],
                    metadata=result["metadatas"][0] if result["metadatas"] else {},
                    embedding=result["embeddings"][0] if result.get("embeddings") else None
                )
        except Exception:
            pass
        return None
    
    def delete(self, doc_ids: List[str]) -> None:
        """
        Delete documents by IDs.
        
        Args:
            doc_ids: List of document IDs to delete
        """
        if doc_ids:
            self.collection.delete(ids=doc_ids)
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Search documents by vector similarity.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filter_dict: Optional metadata filter
            
        Returns:
            List of matching documents sorted by relevance
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_dict
        )
        
        documents = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                doc = Document(
                    id=doc_id,
                    content=results["documents"][0][i],
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                    embedding=results["embeddings"][0][i] if results.get("embeddings") else None
                )
                documents.append(doc)
        
        return documents
    
    def search_by_text(
        self,
        query_text: str,
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Search documents by text query (ChromaDB computes embeddings).
        
        Args:
            query_text: Text query
            top_k: Number of results to return
            filter_dict: Optional metadata filter
            
        Returns:
            List of matching documents sorted by relevance
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k,
            where=filter_dict
        )
        
        documents = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                doc = Document(
                    id=doc_id,
                    content=results["documents"][0][i],
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                    embedding=results["embeddings"][0][i] if results.get("embeddings") else None
                )
                documents.append(doc)
        
        return documents
    
    def get_all(self) -> Iterator[Document]:
        """
        Get all documents from the store.
        
        Yields:
            Document objects
        """
        result = self.collection.get()
        
        if result["ids"]:
            for i, doc_id in enumerate(result["ids"]):
                yield Document(
                    id=doc_id,
                    content=result["documents"][i],
                    metadata=result["metadatas"][i] if result["metadatas"] else {},
                    embedding=result["embeddings"][i] if result.get("embeddings") else None
                )
    
    def count(self) -> int:
        """
        Return the number of documents in the store.
        
        Returns:
            Document count
        """
        return self.collection.count()
    
    def clear(self) -> None:
        """Clear all documents from the store."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": self.distance_metric}
        )
    
    def update(self, documents: List[Document]) -> None:
        """
        Update existing documents.
        
        Args:
            documents: List of Document objects to update
        """
        if not documents:
            return
        
        ids = [doc.id for doc in documents]
        contents = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        embeddings = [doc.embedding for doc in documents if doc.embedding is not None]
        
        if len(embeddings) == len(documents):
            self.collection.update(
                ids=ids,
                documents=contents,
                metadatas=metadatas,
                embeddings=embeddings
            )
        else:
            self.collection.update(
                ids=ids,
                documents=contents,
                metadatas=metadatas
            )
    
    def peek(self, limit: int = 10) -> List[Document]:
        """
        Peek at the first N documents in the collection.
        
        Args:
            limit: Number of documents to peek
            
        Returns:
            List of documents
        """
        result = self.collection.peek(limit=limit)
        
        documents = []
        if result["ids"]:
            for i, doc_id in enumerate(result["ids"]):
                doc = Document(
                    id=doc_id,
                    content=result["documents"][i],
                    metadata=result["metadatas"][i] if result["metadatas"] else {},
                    embedding=result["embeddings"][i] if result.get("embeddings") else None
                )
                documents.append(doc)
        
        return documents
