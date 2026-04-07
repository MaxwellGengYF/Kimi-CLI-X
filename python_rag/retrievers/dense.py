"""Dense retriever implementation using vector embeddings and ChromaDB."""

from typing import List, Dict, Any, Optional, Callable

from python_rag.store.base import Document
from python_rag.store.chroma_store import ChromaDocumentStore
from python_rag.embeddings.base import BaseEmbeddingModel
from python_rag.embeddings.sentence_transformer import MiniLMEmbedding

from .base import BaseRetriever, RetrievedDocument


class DenseRetriever(BaseRetriever):
    """
    Dense retriever using vector embeddings for semantic search.
    
    Uses an embedding model to encode queries and searches against
    a ChromaDB vector store for similarity matching.
    """
    
    def __init__(
        self,
        store: ChromaDocumentStore,
        embedding_model: Optional[BaseEmbeddingModel] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_fn: Optional[Callable[[Document], bool]] = None,
        filter_dict: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize dense retriever.
        
        Args:
            store: ChromaDB document store to search against
            embedding_model: Model for query embedding (defaults to MiniLM)
            top_k: Maximum number of documents to retrieve
            score_threshold: Minimum relevance score (0-1 for cosine similarity)
            filter_fn: Optional function to filter documents
            filter_dict: Optional metadata filter for ChromaDB query
        """
        super().__init__(top_k=top_k, score_threshold=score_threshold, filter_fn=filter_fn)
        
        self.store = store
        self.embedding_model = embedding_model or MiniLMEmbedding()
        self.filter_dict = filter_dict
    
    def retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve relevant documents using vector similarity search.
        
        Args:
            query: The search query string
            
        Returns:
            List of retrieved documents sorted by relevance
        """
        # Encode query to embedding
        query_embedding = self.embedding_model.embed_query(query)
        
        # Search in store
        documents = self.store.search(
            query_embedding=query_embedding,
            top_k=self.top_k,
            filter_dict=self.filter_dict
        )
        
        # Convert to RetrievedDocument with scores
        results = []
        for rank, doc in enumerate(documents, start=1):
            # Calculate similarity score (for ChromaDB, we use 1 - distance)
            # ChromaDB returns results sorted by relevance, so we derive a score
            score = self._calculate_score(rank, len(documents))
            
            retrieved = RetrievedDocument(
                document=doc,
                score=score,
                rank=rank
            )
            results.append(retrieved)
        
        return results
    
    def _calculate_score(self, rank: int, total: int) -> float:
        """
        Calculate relevance score from rank position.
        
        Higher rank (lower number) = higher score.
        Uses exponential decay for score distribution.
        
        Args:
            rank: Position in results (1-based)
            total: Total number of results
            
        Returns:
            Score between 0 and 1
        """
        if total == 0:
            return 0.0
        # Exponential decay: score = exp(-0.1 * (rank - 1))
        import math
        return math.exp(-0.1 * (rank - 1))
    
    def retrieve_with_filter(
        self,
        query: str,
        filter_dict: Dict[str, Any]
    ) -> List[RetrievedDocument]:
        """
        Retrieve documents with temporary metadata filter.
        
        Args:
            query: The search query string
            filter_dict: Metadata filter for this query only
            
        Returns:
            List of retrieved documents
        """
        # Encode query
        query_embedding = self.embedding_model.embed_query(query)
        
        # Search with temporary filter
        documents = self.store.search(
            query_embedding=query_embedding,
            top_k=self.top_k,
            filter_dict=filter_dict
        )
        
        results = []
        for rank, doc in enumerate(documents, start=1):
            score = self._calculate_score(rank, len(documents))
            retrieved = RetrievedDocument(
                document=doc,
                score=score,
                rank=rank
            )
            results.append(retrieved)
        
        return results
    
    def add_documents(self, documents: List[Document]) -> None:
        """
        Add documents to the underlying store.
        
        Convenience method that also generates embeddings if not present.
        
        Args:
            documents: Documents to add
        """
        # Generate embeddings for documents without them
        docs_to_embed = [d for d in documents if d.embedding is None]
        if docs_to_embed:
            contents = [d.content for d in docs_to_embed]
            embeddings = self.embedding_model.embed_documents(contents)
            for doc, emb in zip(docs_to_embed, embeddings):
                doc.embedding = emb
        
        self.store.add(documents)
    
    def index_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> None:
        """
        Index raw texts with auto-generated embeddings.
        
        Args:
            texts: List of text strings to index
            metadatas: Optional metadata for each text
            ids: Optional custom IDs (auto-generated if not provided)
        """
        # Generate embeddings
        embeddings = self.embedding_model.embed_documents(texts)
        
        # Create documents
        documents = []
        for i, (text, embedding) in enumerate(zip(texts, embeddings)):
            doc_id = ids[i] if ids else f"doc_{i}"
            metadata = metadatas[i] if metadatas else {}
            
            doc = Document(
                id=doc_id,
                content=text,
                metadata=metadata,
                embedding=embedding
            )
            documents.append(doc)
        
        self.store.add(documents)
    
    def get_embedding_dim(self) -> int:
        """Get the dimension of embeddings used by this retriever."""
        return self.embedding_model.embedding_dim
    
    def is_available(self) -> bool:
        """Check if retriever is ready (store accessible)."""
        try:
            _ = self.store.count()
            return True
        except Exception:
            return False
