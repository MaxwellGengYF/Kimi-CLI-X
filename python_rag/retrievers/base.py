"""Base interface for document retrievers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Iterator, Callable

from python_rag.store.base import Document


@dataclass
class RetrievedDocument:
    """A document retrieved by a retriever with relevance information."""
    
    document: Document
    score: float
    rank: int
    
    @property
    def id(self) -> str:
        """Get document ID."""
        return self.document.id
    
    @property
    def content(self) -> str:
        """Get document content."""
        return self.document.content
    
    @property
    def metadata(self) -> Dict[str, Any]:
        """Get document metadata."""
        return self.document.metadata
    
    def __repr__(self) -> str:
        return f"RetrievedDocument(id={self.id}, score={self.score:.4f}, rank={self.rank})"


class BaseRetriever(ABC):
    """
    Abstract base class for document retrievers.
    
    A retriever is responsible for finding relevant documents given a query.
    Different implementations may use vector similarity, keyword matching,
    or hybrid approaches.
    """
    
    def __init__(
        self,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_fn: Optional[Callable[[Document], bool]] = None
    ):
        """
        Initialize the retriever.
        
        Args:
            top_k: Maximum number of documents to retrieve
            score_threshold: Minimum relevance score for returned documents
            filter_fn: Optional function to filter documents before returning
        """
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.filter_fn = filter_fn
    
    @abstractmethod
    def retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: The search query string
            
        Returns:
            List of retrieved documents sorted by relevance (highest first)
        """
        pass
    
    def retrieve_with_scores(
        self,
        query: str,
        min_score: Optional[float] = None
    ) -> List[RetrievedDocument]:
        """
        Retrieve documents with relevance scores.
        
        Args:
            query: The search query string
            min_score: Optional override for minimum score threshold
            
        Returns:
            List of retrieved documents with scores
        """
        results = self.retrieve(query)
        
        # Apply score threshold
        threshold = min_score if min_score is not None else self.score_threshold
        if threshold is not None:
            results = [r for r in results if r.score >= threshold]
        
        # Apply custom filter
        if self.filter_fn:
            results = [r for r in results if self.filter_fn(r.document)]
        
        return results
    
    def retrieve_one(self, query: str) -> Optional[RetrievedDocument]:
        """
        Retrieve the single most relevant document.
        
        Args:
            query: The search query string
            
        Returns:
            The most relevant document or None if no results
        """
        results = self.retrieve(query)
        return results[0] if results else None
    
    def batch_retrieve(
        self,
        queries: List[str]
    ) -> List[List[RetrievedDocument]]:
        """
        Retrieve documents for multiple queries.
        
        Args:
            queries: List of query strings
            
        Returns:
            List of retrieval results for each query
        """
        return [self.retrieve(q) for q in queries]
    
    def stream_retrieve(
        self,
        query: str
    ) -> Iterator[RetrievedDocument]:
        """
        Stream retrieved documents one by one.
        
        Args:
            query: The search query string
            
        Yields:
            RetrievedDocument objects in order of relevance
        """
        for doc in self.retrieve(query):
            yield doc
    
    def is_available(self) -> bool:
        """
        Check if the retriever is ready to use.
        
        Returns:
            True if the retriever is properly initialized and available
        """
        return True
