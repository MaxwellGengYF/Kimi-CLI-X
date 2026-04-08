"""Hybrid search combining BM25 keyword search with vector search."""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging
import math

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A search result with its ID and score."""
    id: str
    score: float
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


# Alias for backward compatibility
HybridSearchResult = SearchResult


class BM25Searcher:
    """BM25 keyword-based search."""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 searcher.
        
        Args:
            k1: BM25 parameter (term frequency saturation)
            b: BM25 parameter (length normalization)
        """
        self.k1 = k1
        self.b = b
        self._documents: Dict[str, str] = {}
        self._doc_metadata: Dict[str, Dict[str, Any]] = {}
        self._term_freqs: Dict[str, Dict[str, int]] = {}  # term -> {doc_id: freq}
        self._doc_lengths: Dict[str, int] = {}
        self._avg_doc_length: float = 0.0
        self._doc_count: int = 0
        self._idf: Dict[str, float] = {}
    
    def add_document(self, doc_id: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a document to the index.
        
        Args:
            doc_id: Unique document ID
            content: Document text content
            metadata: Optional metadata
        """
        self._documents[doc_id] = content
        self._doc_metadata[doc_id] = metadata or {}
        
        # Tokenize and compute term frequencies
        tokens = self._tokenize(content)
        doc_length = len(tokens)
        self._doc_lengths[doc_id] = doc_length
        
        # Update term frequencies
        term_freq = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
        
        for term, freq in term_freq.items():
            if term not in self._term_freqs:
                self._term_freqs[term] = {}
            self._term_freqs[term][doc_id] = freq
        
        # Update statistics
        self._doc_count = len(self._documents)
        self._avg_doc_length = sum(self._doc_lengths.values()) / self._doc_count if self._doc_count > 0 else 0
        
        # Update IDF
        self._update_idf()
    
    def add_documents(
        self,
        doc_ids: List[str],
        contents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """Add multiple documents to the index.
        
        Args:
            doc_ids: List of document IDs
            contents: List of document contents
            metadatas: Optional list of metadata dicts
        """
        if metadatas is None:
            metadatas = [None] * len(doc_ids)
        
        for doc_id, content, metadata in zip(doc_ids, contents, metadatas):
            self.add_document(doc_id, content, metadata)
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms.
        
        Args:
            text: Input text
            
        Returns:
            List of tokens
        """
        # Simple tokenization: lowercase, split on non-alphanumeric
        import re
        text = text.lower()
        tokens = re.findall(r'\b[a-z0-9]+\b', text)
        return tokens
    
    def _update_idf(self):
        """Update IDF values for all terms."""
        for term, doc_freqs in self._term_freqs.items():
            # IDF = log((N - n + 0.5) / (n + 0.5))
            n = len(doc_freqs)
            self._idf[term] = math.log(
                (self._doc_count - n + 0.5) / (n + 0.5) + 1
            )
    
    def search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Search for documents matching the query.
        
        Args:
            query: Search query
            top_k: Number of top results to return
            
        Returns:
            List of SearchResult sorted by score (descending)
        """
        if not self._documents:
            return []
        
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        
        scores: Dict[str, float] = {}
        
        for doc_id in self._documents:
            score = 0.0
            doc_length = self._doc_lengths[doc_id]
            
            for term in query_tokens:
                if term not in self._term_freqs or doc_id not in self._term_freqs[term]:
                    continue
                
                tf = self._term_freqs[term][doc_id]
                idf = self._idf.get(term, 0)
                
                # BM25 formula
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self._avg_doc_length))
                score += idf * (numerator / denominator)
            
            if score > 0:
                scores[doc_id] = score
        
        # Sort by score and return top_k
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for doc_id, score in sorted_results[:top_k]:
            results.append(SearchResult(
                id=doc_id,
                score=score,
                content=self._documents.get(doc_id),
                metadata=self._doc_metadata.get(doc_id, {})
            ))
        
        return results
    
    def clear(self):
        """Clear all documents from the index."""
        self._documents.clear()
        self._doc_metadata.clear()
        self._term_freqs.clear()
        self._doc_lengths.clear()
        self._avg_doc_length = 0.0
        self._doc_count = 0
        self._idf.clear()


class ReciprocalRankFusion:
    """Reciprocal Rank Fusion for combining multiple search results."""
    
    def __init__(self, k: float = 60.0):
        """Initialize RRF.
        
        Args:
            k: RRF constant (default: 60)
        """
        self.k = k
    
    def fuse(
        self,
        results_list: List[List[SearchResult]],
        weights: Optional[List[float]] = None
    ) -> List[SearchResult]:
        """Fuse multiple ranked lists using RRF.
        
        Args:
            results_list: List of ranked result lists
            weights: Optional weights for each list (default: equal weights)
            
        Returns:
            Fused and re-ranked results
        """
        if not results_list:
            return []
        
        if weights is None:
            weights = [1.0] * len(results_list)
        
        # Calculate RRF scores
        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, SearchResult] = {}
        
        for results, weight in zip(results_list, weights):
            for rank, result in enumerate(results, start=1):
                doc_id = result.id
                
                # RRF score: weight * (1 / (k + rank))
                rrf_score = weight * (1.0 / (self.k + rank))
                
                if doc_id in rrf_scores:
                    rrf_scores[doc_id] += rrf_score
                else:
                    rrf_scores[doc_id] = rrf_score
                    result_map[doc_id] = result
        
        # Sort by RRF score
        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Build final results
        fused_results = []
        for doc_id, score in sorted_results:
            result = result_map[doc_id]
            fused_results.append(SearchResult(
                id=doc_id,
                score=score,
                content=result.content,
                metadata=result.metadata
            ))
        
        return fused_results


class HybridSearcher:
    """Hybrid search combining BM25 and vector search."""
    
    def __init__(
        self,
        vector_store = None,
        alpha: float = 0.7,
        rrf_k: float = 60.0
    ):
        """Initialize hybrid searcher.
        
        Args:
            vector_store: ChromaVectorStore instance (optional for standalone BM25)
            alpha: Weight for vector search (1-alpha for BM25)
            rrf_k: RRF constant
        """
        self.vector_store = vector_store
        self.alpha = alpha
        self.bm25 = BM25Searcher()
        self.rrf = ReciprocalRankFusion(k=rrf_k)
        self._bm25_indexed = False
        # Standalone corpus storage
        self._corpus: Dict[str, Dict[str, Any]] = {}
    
    def index_documents(
        self,
        doc_ids: List[str],
        contents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """Index documents for BM25 search.
        
        This should be called after adding documents to vector store.
        
        Args:
            doc_ids: List of document IDs
            contents: List of document contents
            metadatas: Optional list of metadata
        """
        self.bm25.add_documents(doc_ids, contents, metadatas)
        self._bm25_indexed = True
    
    def build_corpus(self, documents: List[Dict[str, Any]]) -> None:
        """Build corpus for standalone hybrid search.
        
        This allows using HybridSearcher without a vector store,
        relying on in-memory storage for documents.
        
        Args:
            documents: List of document dicts with 'id', 'text', and optional 'metadata'
        """
        self._corpus = {}
        doc_ids = []
        contents = []
        metadatas = []
        
        for doc in documents:
            doc_id = doc.get("id", f"doc_{len(doc_ids)}")
            self._corpus[doc_id] = doc
            doc_ids.append(doc_id)
            contents.append(doc.get("text", ""))
            metadatas.append(doc.get("metadata", {}))
        
        self.index_documents(doc_ids, contents, metadatas)
    
    def clear(self) -> None:
        """Clear all indexed data."""
        self._corpus.clear()
        self.bm25 = BM25Searcher()
        self._bm25_indexed = False
    
    def search(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Perform hybrid search.
        
        Args:
            query: Raw query text for BM25
            query_embedding: Query embedding for vector search (optional for BM25-only)
            top_k: Number of results to return
            filter_dict: Optional metadata filter for vector search
            
        Returns:
            List of SearchResult sorted by fused score
        """
        # Vector search (if vector store and embedding available)
        vector_results = []
        if self.vector_store is not None and query_embedding is not None:
            vector_results = self._vector_search(query_embedding, top_k * 2, filter_dict)
        elif self._corpus and query_embedding is not None:
            # Simple vector search on corpus if no vector store
            vector_results = self._corpus_vector_search(query_embedding, top_k * 2)
        
        # BM25 search
        bm25_results = []
        if self._bm25_indexed:
            bm25_results = self.bm25.search(query, top_k=top_k * 2)
        
        # If only one method has results, return those
        if not bm25_results:
            return vector_results[:top_k] if vector_results else []
        if not vector_results:
            return bm25_results[:top_k]
        
        # Fuse results using RRF
        weights = [self.alpha, 1.0 - self.alpha]  # [vector_weight, bm25_weight]
        fused_results = self.rrf.fuse([vector_results, bm25_results], weights)
        
        return fused_results[:top_k]
    
    def _vector_search(
        self,
        query_embedding: List[float],
        n_results: int,
        filter_dict: Optional[Dict[str, Any]]
    ) -> List[SearchResult]:
        """Search using vector store."""
        vector_results_raw = self.vector_store.query(
            query_embedding=query_embedding,
            n_results=n_results,
            filter_dict=filter_dict
        )
        
        vector_results = []
        if vector_results_raw.get("ids") and vector_results_raw["ids"][0]:
            for i, doc_id in enumerate(vector_results_raw["ids"][0]):
                # Convert distance to similarity score (cosine distance -> similarity)
                distance = vector_results_raw["distances"][0][i] if vector_results_raw.get("distances") else 0.5
                similarity = 1.0 - distance
                
                vector_results.append(SearchResult(
                    id=doc_id,
                    score=similarity,
                    content=vector_results_raw["documents"][0][i] if vector_results_raw.get("documents") else None,
                    metadata=vector_results_raw["metadatas"][0][i] if vector_results_raw.get("metadatas") else {}
                ))
        
        return vector_results
    
    def _corpus_vector_search(
        self,
        query_embedding: List[float],
        n_results: int
    ) -> List[SearchResult]:
        """Fallback vector search on in-memory corpus using simple dot product."""
        import numpy as np
        
        results = []
        query_vec = np.array(query_embedding)
        
        for doc_id, doc in self._corpus.items():
            # Generate simple embedding from text (fallback)
            doc_text = doc.get("text", "")
            # Simple bag-of-words style similarity
            score = self._text_similarity(query_vec, doc_text)
            
            results.append(SearchResult(
                id=doc_id,
                score=score,
                content=doc_text,
                metadata=doc.get("metadata", {})
            ))
        
        # Sort by score and return top n
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:n_results]
    
    def _text_similarity(self, query_vec: np.ndarray, text: str) -> float:
        """Compute simple similarity between query vector and text."""
        import numpy as np
        # Simple character n-gram based similarity as fallback
        text_vec = np.zeros_like(query_vec)
        
        # Use character trigrams as features
        text = text.lower()
        for i in range(len(text) - 2):
            trigram = text[i:i+3]
            idx = hash(trigram) % len(text_vec)
            text_vec[idx] += 1
        
        # Normalize
        norm = np.linalg.norm(text_vec)
        if norm > 0:
            text_vec = text_vec / norm
        
        # Cosine similarity
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0 and norm > 0:
            return float(np.dot(query_vec, text_vec) / query_norm)
        return 0.0


def hybrid_query(
    vector_store,
    embedder,
    query_text: str,
    top_k: int = 10,
    alpha: float = 0.7,
    filter_dict: Optional[Dict[str, Any]] = None
) -> List[SearchResult]:
    """Convenience function for hybrid search.
    
    Args:
        vector_store: ChromaVectorStore instance
        embedder: Embedding service (must have embed_query method)
        query_text: Search query
        top_k: Number of results
        alpha: Weight for vector search (1-alpha for BM25)
        filter_dict: Optional metadata filter
        
    Returns:
        List of SearchResult
    """
    # Generate query embedding
    query_embedding = embedder.embed_query(query_text)
    
    # Create hybrid searcher
    searcher = HybridSearcher(vector_store, alpha=alpha)
    
    # Note: BM25 index needs to be built separately by calling index_documents
    # This function only performs the search with existing indices
    
    return searcher.search(query_text, query_embedding, top_k, filter_dict)
