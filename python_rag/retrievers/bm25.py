"""BM25 retriever implementation using rank-bm25 for sparse retrieval."""

import re
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict

from python_rag.store.base import Document

from .base import BaseRetriever, RetrievedDocument


class BM25Retriever(BaseRetriever):
    """
    Sparse retriever using BM25 algorithm for lexical matching.
    
    BM25 is a bag-of-words retrieval function that ranks documents based on
    term frequency and inverse document frequency. Good for exact keyword
    matching and when domain-specific vocabulary is important.
    """
    
    def __init__(
        self,
        documents: Optional[List[Document]] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_fn: Optional[Callable[[Document], bool]] = None,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: Optional[Callable[[str], List[str]]] = None
    ):
        """
        Initialize BM25 retriever.
        
        Args:
            documents: Initial documents to index
            top_k: Maximum number of documents to retrieve
            score_threshold: Minimum BM25 score for returned documents
            filter_fn: Optional function to filter documents
            k1: BM25 parameter controlling term frequency saturation (default 1.5)
            b: BM25 parameter controlling document length normalization (default 0.75)
            tokenizer: Custom tokenization function (default: lowercase + word extraction)
        """
        super().__init__(top_k=top_k, score_threshold=score_threshold, filter_fn=filter_fn)
        
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or self._default_tokenizer
        
        # Storage
        self.documents: Dict[str, Document] = {}
        self.tokenized_docs: Dict[str, List[str]] = {}
        self.doc_count = 0
        self.avg_doc_length = 0.0
        
        # Index structures
        self.inverted_index: Dict[str, set] = defaultdict(set)  # term -> doc_ids
        self.term_freq: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.doc_freq: Dict[str, int] = {}  # term -> number of docs containing term
        
        # Precompute IDF values
        self.idf: Dict[str, float] = {}
        
        # Index initial documents if provided
        if documents:
            self.add_documents(documents)
    
    @staticmethod
    def _default_tokenizer(text: str) -> List[str]:
        """
        Default tokenizer: lowercase and extract alphanumeric words.
        
        Args:
            text: Input text
            
        Returns:
            List of tokens
        """
        text = text.lower()
        # Extract alphanumeric sequences (words with optional apostrophes)
        tokens = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)
        return tokens
    
    def add_documents(self, documents: List[Document]) -> None:
        """
        Add documents to the BM25 index.
        
        Args:
            documents: Documents to add
        """
        for doc in documents:
            if doc.id in self.documents:
                # Skip duplicates or implement update logic
                continue
            
            self.documents[doc.id] = doc
            tokens = self.tokenizer(doc.content)
            self.tokenized_docs[doc.id] = tokens
            
            # Update inverted index
            unique_terms = set(tokens)
            for term in unique_terms:
                self.inverted_index[term].add(doc.id)
                self.term_freq[doc.id][term] = tokens.count(term)
            
            self.doc_count += 1
        
        # Recompute statistics
        self._update_statistics()
    
    def _update_statistics(self) -> None:
        """Update document statistics and IDF values."""
        if self.doc_count == 0:
            return
        
        # Average document length
        total_length = sum(len(tokens) for tokens in self.tokenized_docs.values())
        self.avg_doc_length = total_length / self.doc_count
        
        # Document frequencies
        self.doc_freq = {
            term: len(doc_ids) 
            for term, doc_ids in self.inverted_index.items()
        }
        
        # Compute IDF values
        self.idf = {}
        for term, df in self.doc_freq.items():
            # BM25 IDF formula with smoothing
            idf = self._compute_idf(df, self.doc_count)
            self.idf[term] = idf
    
    def _compute_idf(self, doc_freq: int, total_docs: int) -> float:
        """
        Compute IDF score for a term.
        
        Uses BM25's variant of IDF with floor at 0.
        
        Args:
            doc_freq: Number of documents containing the term
            total_docs: Total number of documents
            
        Returns:
            IDF score
        """
        import math
        # BM25 IDF: log((N - n + 0.5) / (n + 0.5) + 1)
        idf = math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
        return max(0, idf)  # Floor at 0
    
    def _compute_bm25_score(self, doc_id: str, query_terms: List[str]) -> float:
        """
        Compute BM25 score for a document and query.
        
        Args:
            doc_id: Document ID
            query_terms: Tokenized query terms
            
        Returns:
            BM25 score
        """
        if doc_id not in self.tokenized_docs:
            return 0.0
        
        doc_length = len(self.tokenized_docs[doc_id])
        score = 0.0
        
        for term in query_terms:
            if term not in self.idf:
                continue
            
            tf = self.term_freq[doc_id].get(term, 0)
            idf = self.idf[term]
            
            # BM25 scoring formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self.avg_doc_length))
            
            score += idf * (numerator / denominator)
        
        return score
    
    def retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve relevant documents using BM25 scoring.
        
        Args:
            query: The search query string
            
        Returns:
            List of retrieved documents sorted by BM25 score
        """
        if self.doc_count == 0:
            return []
        
        # Tokenize query
        query_terms = self.tokenizer(query)
        if not query_terms:
            return []
        
        # Find candidate documents (contain at least one query term)
        candidate_ids = set()
        for term in query_terms:
            candidate_ids.update(self.inverted_index.get(term, set()))
        
        # Apply custom filter
        if self.filter_fn:
            candidate_ids = {
                doc_id for doc_id in candidate_ids 
                if self.filter_fn(self.documents[doc_id])
            }
        
        # Score candidates
        scored_docs = []
        for doc_id in candidate_ids:
            score = self._compute_bm25_score(doc_id, query_terms)
            if self.score_threshold is None or score >= self.score_threshold:
                scored_docs.append((doc_id, score))
        
        # Sort by score descending
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        # Take top_k
        top_results = scored_docs[:self.top_k]
        
        # Build result list
        results = []
        for rank, (doc_id, score) in enumerate(top_results, start=1):
            retrieved = RetrievedDocument(
                document=self.documents[doc_id],
                score=score,
                rank=rank
            )
            results.append(retrieved)
        
        return results
    
    def delete(self, doc_ids: List[str]) -> None:
        """
        Remove documents from the index.
        
        Args:
            doc_ids: List of document IDs to remove
        """
        for doc_id in doc_ids:
            if doc_id not in self.documents:
                continue
            
            # Remove from inverted index
            tokens = self.tokenized_docs.get(doc_id, [])
            for term in set(tokens):
                self.inverted_index[term].discard(doc_id)
                if not self.inverted_index[term]:
                    del self.inverted_index[term]
            
            # Remove document data
            del self.documents[doc_id]
            del self.tokenized_docs[doc_id]
            if doc_id in self.term_freq:
                del self.term_freq[doc_id]
            
            self.doc_count -= 1
        
        # Recompute statistics
        self._update_statistics()
    
    def clear(self) -> None:
        """Clear all documents from the index."""
        self.documents.clear()
        self.tokenized_docs.clear()
        self.inverted_index.clear()
        self.term_freq.clear()
        self.doc_freq.clear()
        self.idf.clear()
        self.doc_count = 0
        self.avg_doc_length = 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get index statistics.
        
        Returns:
            Dictionary with index statistics
        """
        total_terms = sum(len(tokens) for tokens in self.tokenized_docs.values())
        unique_terms = len(self.inverted_index)
        
        return {
            "document_count": self.doc_count,
            "total_terms": total_terms,
            "unique_terms": unique_terms,
            "avg_doc_length": self.avg_doc_length,
            "k1": self.k1,
            "b": self.b,
        }
    
    def is_available(self) -> bool:
        """Check if retriever has indexed documents."""
        return self.doc_count > 0
