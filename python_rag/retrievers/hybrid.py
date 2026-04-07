"""Hybrid retriever combining Dense and BM25 with fusion scoring."""

from typing import List, Dict, Any, Optional, Callable, Tuple
from collections import defaultdict

from python_rag.store.base import Document

from .base import BaseRetriever, RetrievedDocument
from .dense import DenseRetriever
from .bm25 import BM25Retriever


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever combining dense (vector) and sparse (BM25) retrieval.
    
    Uses fusion scoring (Reciprocal Rank Fusion by default) to combine
    results from both retrievers, leveraging semantic similarity from
    dense retrieval and exact keyword matching from BM25.
    """
    
    def __init__(
        self,
        dense_retriever: Optional[DenseRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_fn: Optional[Callable[[Document], bool]] = None,
        fusion_method: str = "rrf",
        rrf_k: int = 60,
        dense_weight: float = 0.5,
        bm25_weight: float = 0.5,
        normalize_scores: bool = True
    ):
        """
        Initialize hybrid retriever.
        
        Args:
            dense_retriever: Dense (vector) retriever instance
            bm25_retriever: BM25 (sparse) retriever instance
            top_k: Maximum number of documents to retrieve
            score_threshold: Minimum fusion score for returned documents
            filter_fn: Optional function to filter documents
            fusion_method: Fusion method - 'rrf' (reciprocal rank) or 'linear'
            rrf_k: RRF constant (default 60, higher = less rank bias)
            dense_weight: Weight for dense scores in linear fusion (0-1)
            bm25_weight: Weight for BM25 scores in linear fusion (0-1)
            normalize_scores: Whether to normalize scores before fusion
        """
        super().__init__(top_k=top_k, score_threshold=score_threshold, filter_fn=filter_fn)
        
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        
        self.fusion_method = fusion_method.lower()
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.normalize_scores = normalize_scores
        
        # Validate fusion method
        if self.fusion_method not in ("rrf", "linear"):
            raise ValueError(f"Unknown fusion method: {fusion_method}. Use 'rrf' or 'linear'.")
        
        # Validate weights for linear fusion
        if self.fusion_method == "linear":
            total_weight = self.dense_weight + self.bm25_weight
            if abs(total_weight - 1.0) > 1e-6:
                # Normalize weights to sum to 1
                self.dense_weight /= total_weight
                self.bm25_weight /= total_weight
    
    def retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve documents using both dense and sparse methods with fusion.
        
        Args:
            query: The search query string
            
        Returns:
            List of retrieved documents sorted by fusion score
        """
        # Get results from both retrievers
        dense_results: List[RetrievedDocument] = []
        bm25_results: List[RetrievedDocument] = []
        
        if self.dense_retriever:
            dense_results = self.dense_retriever.retrieve(query)
        
        if self.bm25_retriever:
            bm25_results = self.bm25_retriever.retrieve(query)
        
        # Fuse results
        fused_results = self._fuse_results(dense_results, bm25_results)
        
        # Apply threshold and filter
        if self.score_threshold is not None:
            fused_results = [r for r in fused_results if r.score >= self.score_threshold]
        
        if self.filter_fn:
            fused_results = [r for r in fused_results if self.filter_fn(r.document)]
        
        # Limit to top_k
        return fused_results[:self.top_k]
    
    def _fuse_results(
        self,
        dense_results: List[RetrievedDocument],
        bm25_results: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """
        Fuse results from dense and BM25 retrievers.
        
        Args:
            dense_results: Results from dense retriever
            bm25_results: Results from BM25 retriever
            
        Returns:
            Fused and re-ranked results
        """
        if not dense_results and not bm25_results:
            return []
        
        if not dense_results:
            return bm25_results
        if not bm25_results:
            return dense_results
        
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(dense_results, bm25_results)
        else:
            return self._linear_fusion(dense_results, bm25_results)
    
    def _reciprocal_rank_fusion(
        self,
        dense_results: List[RetrievedDocument],
        bm25_results: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).
        
        RRF formula: score = sum(1 / (k + rank)) for each list containing the doc
        
        Args:
            dense_results: Results from dense retriever
            bm25_results: Results from BM25 retriever
            
        Returns:
            Re-ranked results by RRF score
        """
        # Build rank maps
        dense_ranks = {r.id: r.rank for r in dense_results}
        bm25_ranks = {r.id: r.rank for r in bm25_results}
        
        # Collect all unique documents
        all_docs = {}
        for r in dense_results:
            all_docs[r.id] = r.document
        for r in bm25_results:
            all_docs[r.id] = r.document
        
        # Calculate RRF scores
        rrf_scores = {}
        for doc_id in all_docs:
            score = 0.0
            
            # Contribution from dense retriever
            if doc_id in dense_ranks:
                score += 1.0 / (self.rrf_k + dense_ranks[doc_id])
            
            # Contribution from BM25 retriever
            if doc_id in bm25_ranks:
                score += 1.0 / (self.rrf_k + bm25_ranks[doc_id])
            
            rrf_scores[doc_id] = score
        
        # Sort by RRF score
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build result list
        results = []
        for rank, (doc_id, score) in enumerate(sorted_docs, start=1):
            retrieved = RetrievedDocument(
                document=all_docs[doc_id],
                score=score,
                rank=rank
            )
            results.append(retrieved)
        
        return results
    
    def _linear_fusion(
        self,
        dense_results: List[RetrievedDocument],
        bm25_results: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """
        Combine results using weighted linear fusion of scores.
        
        Args:
            dense_results: Results from dense retriever
            bm25_results: Results from BM25 retriever
            
        Returns:
            Re-ranked results by fused score
        """
        # Normalize scores if requested
        if self.normalize_scores:
            dense_results = self._normalize_result_scores(dense_results)
            bm25_results = self._normalize_result_scores(bm25_results)
        
        # Collect scores from both retrievers
        all_docs = {}
        dense_scores = {}
        bm25_scores = {}
        
        for r in dense_results:
            all_docs[r.id] = r.document
            dense_scores[r.id] = r.score
        
        for r in bm25_results:
            all_docs[r.id] = r.document
            bm25_scores[r.id] = r.score
        
        # Calculate fused scores
        fused_scores = {}
        for doc_id in all_docs:
            d_score = dense_scores.get(doc_id, 0.0)
            b_score = bm25_scores.get(doc_id, 0.0)
            
            # Weighted combination
            fused_score = (self.dense_weight * d_score + 
                          self.bm25_weight * b_score)
            fused_scores[doc_id] = fused_score
        
        # Sort by fused score
        sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build result list
        results = []
        for rank, (doc_id, score) in enumerate(sorted_docs, start=1):
            retrieved = RetrievedDocument(
                document=all_docs[doc_id],
                score=score,
                rank=rank
            )
            results.append(retrieved)
        
        return results
    
    def _normalize_result_scores(
        self,
        results: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """
        Normalize scores to 0-1 range using min-max normalization.
        
        Args:
            results: List of retrieved documents
            
        Returns:
            Results with normalized scores
        """
        if not results:
            return results
        
        scores = [r.score for r in results]
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            # All scores are the same
            return results
        
        normalized = []
        for r in results:
            norm_score = (r.score - min_score) / (max_score - min_score)
            normalized.append(RetrievedDocument(
                document=r.document,
                score=norm_score,
                rank=r.rank
            ))
        
        return normalized
    
    def add_documents(self, documents: List[Document]) -> None:
        """
        Add documents to underlying retrievers.
        
        Args:
            documents: Documents to add
        """
        if self.dense_retriever:
            self.dense_retriever.add_documents(documents)
        
        if self.bm25_retriever:
            self.bm25_retriever.add_documents(documents)
    
    def index_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> None:
        """
        Index raw texts in both retrievers.
        
        Note: This creates Document objects and indexes them in both retrievers.
        For large datasets, consider indexing separately for each retriever type.
        
        Args:
            texts: List of text strings to index
            metadatas: Optional metadata for each text
            ids: Optional custom IDs
        """
        # Generate IDs if not provided
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(texts))]
        
        # Create documents for BM25 retriever
        documents = []
        for i, text in enumerate(texts):
            metadata = metadatas[i] if metadatas else {}
            doc = Document(
                id=ids[i],
                content=text,
                metadata=metadata
            )
            documents.append(doc)
        
        # Add to BM25 retriever
        if self.bm25_retriever:
            self.bm25_retriever.add_documents(documents)
        
        # Index in dense retriever (handles embedding generation)
        if self.dense_retriever:
            self.dense_retriever.index_texts(
                texts=texts,
                metadatas=metadatas,
                ids=ids
            )
    
    def get_retriever_stats(self) -> Dict[str, Any]:
        """
        Get statistics from underlying retrievers.
        
        Returns:
            Dictionary with statistics for each retriever
        """
        stats = {
            "fusion_method": self.fusion_method,
            "rrf_k": self.rrf_k,
            "dense_weight": self.dense_weight,
            "bm25_weight": self.bm25_weight,
        }
        
        if self.dense_retriever:
            stats["dense"] = {
                "available": self.dense_retriever.is_available(),
                "embedding_dim": self.dense_retriever.get_embedding_dim(),
            }
        
        if self.bm25_retriever:
            stats["bm25"] = self.bm25_retriever.get_stats()
        
        return stats
    
    def is_available(self) -> bool:
        """Check if at least one underlying retriever is available."""
        dense_ok = self.dense_retriever is not None and self.dense_retriever.is_available()
        bm25_ok = self.bm25_retriever is not None and self.bm25_retriever.is_available()
        return dense_ok or bm25_ok
