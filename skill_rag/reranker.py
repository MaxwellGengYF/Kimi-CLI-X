"""Reranker module for improving retrieval quality using cross-encoders."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RankedDocument:
    """A document with its relevance score from reranking."""
    content: str
    metadata: Dict[str, Any]
    score: float
    original_rank: int
    source: str = ""
    start_line: int = 0
    end_line: int = 0


class Reranker(ABC):
    """Abstract base class for rerankers."""
    
    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
        metadata_list: Optional[List[Dict[str, Any]]] = None
    ) -> List[RankedDocument]:
        """Rerank documents based on query relevance.
        
        Args:
            query: The search query
            documents: List of document contents to rerank
            top_k: Number of top documents to return after reranking
            metadata_list: Optional metadata for each document
            
        Returns:
            List of RankedDocument sorted by relevance score (descending)
        """
        pass


class CrossEncoderReranker(Reranker):
    """Reranker using cross-encoder models for precise relevance scoring."""
    
    # Default models (lightweight, good performance)
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ALTERNATIVE_MODEL = "BAAI/bge-reranker-base"
    
    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        """Initialize the reranker.
        
        Args:
            model_name: Name of the cross-encoder model to use
            device: Device to run on ('cpu', 'cuda', or None for auto)
        """
        self._model_name = model_name or self.DEFAULT_MODEL
        self._device = device
        self._model = None
    
    def _get_model(self):
        """Lazy load the cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                
                logger.info(f"Loading cross-encoder model: {self._model_name}")
                self._model = CrossEncoder(self._model_name, device=self._device)
                logger.info("Cross-encoder model loaded successfully")
            except ImportError:
                logger.error(
                    "sentence-transformers not available. "
                    "Install with: pip install sentence-transformers"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to load cross-encoder model: {e}")
                raise
        return self._model
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
        metadata_list: Optional[List[Dict[str, Any]]] = None
    ) -> List[RankedDocument]:
        """Rerank documents based on query relevance.
        
        Args:
            query: The search query
            documents: List of document contents to rerank
            top_k: Number of top documents to return after reranking
            metadata_list: Optional metadata for each document
            
        Returns:
            List of RankedDocument sorted by relevance score (descending)
        """
        if not documents:
            return []
        
        if metadata_list is None:
            metadata_list = [{} for _ in documents]
        
        # Ensure metadata list matches documents
        while len(metadata_list) < len(documents):
            metadata_list.append({})
        
        model = self._get_model()
        
        # Create query-document pairs
        pairs = [(query, doc) for doc in documents]
        
        # Get relevance scores from cross-encoder
        scores = model.predict(pairs)
        
        # Create ranked documents
        ranked_docs = []
        for i, (doc, score, meta) in enumerate(zip(documents, scores, metadata_list)):
            ranked_docs.append(RankedDocument(
                content=doc,
                metadata=meta,
                score=float(score),
                original_rank=i,
                source=meta.get("source", ""),
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0)
            ))
        
        # Sort by score descending
        ranked_docs.sort(key=lambda x: x.score, reverse=True)
        
        # Return top_k
        return ranked_docs[:top_k]
    
    def rerank_results(
        self,
        query: str,
        query_results: Dict[str, Any],
        top_k: int = 5
    ) -> List[RankedDocument]:
        """Rerank query results from vector store.
        
        Args:
            query: The search query
            query_results: Results from ChromaVectorStore.query()
            top_k: Number of top documents to return after reranking
            
        Returns:
            List of RankedDocument sorted by relevance score (descending)
        """
        documents = query_results.get("documents", [[]])[0] or []
        metadatas = query_results.get("metadatas", [[]])[0] or []
        
        if not documents:
            return []
        
        return self.rerank(query, documents, top_k, metadatas)


class SimpleReranker(Reranker):
    """Simple reranker using keyword matching as fallback."""
    
    def __init__(self):
        """Initialize simple reranker."""
        pass
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
        metadata_list: Optional[List[Dict[str, Any]]] = None
    ) -> List[RankedDocument]:
        """Rerank documents based on keyword overlap.
        
        This is a simple fallback that doesn't require any ML model.
        Uses TF-IDF-like scoring based on term frequency.
        
        Args:
            query: The search query
            documents: List of document contents to rerank
            top_k: Number of top documents to return
            metadata_list: Optional metadata for each document
            
        Returns:
            List of RankedDocument sorted by relevance score (descending)
        """
        if not documents:
            return []
        
        if metadata_list is None:
            metadata_list = [{} for _ in documents]
        
        # Tokenize query (simple word split)
        query_terms = set(query.lower().split())
        
        ranked_docs = []
        for i, (doc, meta) in enumerate(zip(documents, metadata_list)):
            doc_terms = set(doc.lower().split())
            
            # Calculate overlap score
            overlap = len(query_terms & doc_terms)
            query_coverage = overlap / len(query_terms) if query_terms else 0
            
            # Simple score: coverage * overlap count
            score = query_coverage * overlap
            
            ranked_docs.append(RankedDocument(
                content=doc,
                metadata=meta,
                score=score,
                original_rank=i,
                source=meta.get("source", ""),
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0)
            ))
        
        # Sort by score descending
        ranked_docs.sort(key=lambda x: x.score, reverse=True)
        
        return ranked_docs[:top_k]
    
    def rerank_results(
        self,
        query: str,
        query_results: Dict[str, Any],
        top_k: int = 5
    ) -> List[RankedDocument]:
        """Rerank query results from vector store.
        
        Args:
            query: The search query
            query_results: Results from ChromaVectorStore.query()
            top_k: Number of top documents to return after reranking
            
        Returns:
            List of RankedDocument sorted by relevance score (descending)
        """
        documents = query_results.get("documents", [[]])[0] or []
        metadatas = query_results.get("metadatas", [[]])[0] or []
        
        if not documents:
            return []
        
        return self.rerank(query, documents, top_k, metadatas)


def create_reranker(
    model_name: Optional[str] = None,
    use_cross_encoder: bool = True,
    device: Optional[str] = None
) -> Reranker:
    """Factory function to create a reranker.
    
    Args:
        model_name: Name of the cross-encoder model (if using cross-encoder)
        use_cross_encoder: Whether to use cross-encoder (requires sentence-transformers)
        device: Device to run on ('cpu', 'cuda', or None for auto)
        
    Returns:
        Reranker instance
    """
    if use_cross_encoder:
        try:
            return CrossEncoderReranker(model_name=model_name, device=device)
        except Exception as e:
            logger.warning(f"Failed to create cross-encoder reranker: {e}. Using simple reranker.")
            return SimpleReranker()
    else:
        return SimpleReranker()
