"""Maximal Marginal Relevance (MMR) for result diversification.

MMR provides a way to balance relevance and diversity in search results,
ensuring that retrieved documents cover different aspects of the query.
"""

from dataclasses import dataclass
from typing import List, Optional, Callable, Any
import numpy as np

from skill_rag.config import get_config


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Cosine similarity in range [-1, 1]
    """
    a_norm = a / (np.linalg.norm(a) + 1e-8)
    b_norm = b / (np.linalg.norm(b) + 1e-8)
    return float(np.dot(a_norm, b_norm))


@dataclass
class MMRResult:
    """Result from MMR diversification."""
    document: Any
    score: float
    relevance_score: float
    diversity_score: float
    rank: int


class MMREngine:
    """Maximal Marginal Relevance engine for diversifying results.
    
    MMR balances relevance to the query with diversity among selected results.
    Higher lambda values prioritize relevance, lower values prioritize diversity.
    
    Example:
        >>> engine = MMREngine(lambda_param=0.5)
        >>> results = engine.diversify(
        ...     query_embedding=query_emb,
        ...     candidates=candidates,
        ...     get_embedding_fn=lambda doc: doc.embedding,
        ...     k=5
        ... )
    """
    
    def __init__(
        self,
        lambda_param: float = 0.5,
        similarity_fn: Optional[Callable[[np.ndarray, np.ndarray], float]] = None
    ):
        """Initialize MMR engine.
        
        Args:
            lambda_param: Trade-off between relevance (1.0) and diversity (0.0)
            similarity_fn: Function to compute similarity between embeddings
        """
        if not 0 <= lambda_param <= 1:
            raise ValueError(f"lambda_param must be in [0, 1], got {lambda_param}")
        
        self.lambda_param = lambda_param
        self.similarity_fn = similarity_fn or cosine_similarity
    
    def diversify(
        self,
        query_embedding: np.ndarray,
        candidates: List[Any],
        get_embedding_fn: Callable[[Any], np.ndarray],
        k: int = 5,
        initial_scores: Optional[List[float]] = None
    ) -> List[MMRResult]:
        """Select k diverse and relevant results using MMR.
        
        Args:
            query_embedding: Query embedding vector
            candidates: List of candidate documents/results
            get_embedding_fn: Function to get embedding from a candidate
            k: Number of results to select
            initial_scores: Optional initial relevance scores for candidates
            
        Returns:
            List of MMRResult objects ordered by selection
        """
        if not candidates:
            return []
        
        k = min(k, len(candidates))
        
        # Get embeddings for all candidates
        candidate_embeddings = [
            get_embedding_fn(doc) for doc in candidates
        ]
        
        # Compute relevance scores if not provided
        if initial_scores is None:
            relevance_scores = [
                self.similarity_fn(query_embedding, emb)
                for emb in candidate_embeddings
            ]
        else:
            # Normalize initial scores to [0, 1] range
            min_score = min(initial_scores)
            max_score = max(initial_scores)
            if max_score > min_score:
                relevance_scores = [
                    (s - min_score) / (max_score - min_score)
                    for s in initial_scores
                ]
            else:
                relevance_scores = [1.0] * len(initial_scores)
        
        # Track selected and remaining indices
        selected: List[int] = []
        remaining: set = set(range(len(candidates)))
        
        results: List[MMRResult] = []
        
        for rank in range(1, k + 1):
            if not remaining:
                break
            
            best_idx = None
            best_mmr_score = float('-inf')
            
            for idx in remaining:
                relevance = relevance_scores[idx]
                
                if not selected:
                    # First selection: pure relevance
                    mmr_score = relevance
                    diversity = 0.0
                else:
                    # Compute max similarity to already selected documents
                    max_sim = max(
                        self.similarity_fn(
                            candidate_embeddings[idx],
                            candidate_embeddings[sel_idx]
                        )
                        for sel_idx in selected
                    )
                    diversity = 1.0 - max_sim  # Convert similarity to diversity
                    
                    # MMR formula: λ * relevance - (1-λ) * max_sim
                    mmr_score = (
                        self.lambda_param * relevance -
                        (1 - self.lambda_param) * max_sim
                    )
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx
            
            if best_idx is not None:
                selected.append(best_idx)
                remaining.remove(best_idx)
                
                # Compute final scores for the result
                final_relevance = relevance_scores[best_idx]
                if len(selected) > 1:
                    # Recompute diversity for reporting
                    max_sim = max(
                        self.similarity_fn(
                            candidate_embeddings[best_idx],
                            candidate_embeddings[sel_idx]
                        )
                        for sel_idx in selected[:-1]
                    )
                    final_diversity = 1.0 - max_sim
                else:
                    final_diversity = 1.0
                
                results.append(MMRResult(
                    document=candidates[best_idx],
                    score=best_mmr_score,
                    relevance_score=final_relevance,
                    diversity_score=final_diversity,
                    rank=rank
                ))
        
        return results
    
    def diversify_vectors(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: List[np.ndarray],
        k: int = 5,
        initial_scores: Optional[List[float]] = None
    ) -> List[tuple[int, float]]:
        """Select k diverse vectors using MMR.
        
        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embedding vectors
            k: Number of results to select
            initial_scores: Optional initial relevance scores
            
        Returns:
            List of (index, mmr_score) tuples
        """
        if not candidate_embeddings:
            return []
        
        k = min(k, len(candidate_embeddings))
        
        # Compute relevance scores if not provided
        if initial_scores is None:
            relevance_scores = [
                self.similarity_fn(query_embedding, emb)
                for emb in candidate_embeddings
            ]
        else:
            min_score = min(initial_scores)
            max_score = max(initial_scores)
            if max_score > min_score:
                relevance_scores = [
                    (s - min_score) / (max_score - min_score)
                    for s in initial_scores
                ]
            else:
                relevance_scores = [1.0] * len(initial_scores)
        
        selected: List[int] = []
        remaining: set = set(range(len(candidate_embeddings)))
        
        results: List[tuple[int, float]] = []
        
        for _ in range(k):
            if not remaining:
                break
            
            best_idx = None
            best_mmr_score = float('-inf')
            
            for idx in remaining:
                relevance = relevance_scores[idx]
                
                if not selected:
                    mmr_score = relevance
                else:
                    max_sim = max(
                        self.similarity_fn(
                            candidate_embeddings[idx],
                            candidate_embeddings[sel_idx]
                        )
                        for sel_idx in selected
                    )
                    mmr_score = (
                        self.lambda_param * relevance -
                        (1 - self.lambda_param) * max_sim
                    )
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx
            
            if best_idx is not None:
                selected.append(best_idx)
                remaining.remove(best_idx)
                results.append((best_idx, best_mmr_score))
        
        return results


class MMRDiversifier:
    """High-level diversifier that integrates with vector search results.
    
    This class provides a convenient interface for diversifying search results
    from vector stores or other retrieval systems.
    
    Example:
        >>> diversifier = MMRDiversifier(lambda_param=0.7)
        >>> diversified = diversifier.diversify_results(
        ...     query_embedding=query_emb,
        ...     results=search_results,
        ...     k=5
        ... )
    """
    
    def __init__(
        self,
        lambda_param: float = 0.5,
        similarity_fn: Optional[Callable[[np.ndarray, np.ndarray], float]] = None
    ):
        """Initialize MMR diversifier.
        
        Args:
            lambda_param: Trade-off between relevance and diversity
            similarity_fn: Optional custom similarity function
        """
        self.engine = MMREngine(lambda_param, similarity_fn)
    
    def diversify_results(
        self,
        query_embedding: np.ndarray,
        results: List[dict],
        k: int = 5,
        embedding_key: str = "embedding",
        score_key: Optional[str] = "score"
    ) -> List[dict]:
        """Diversify search results using MMR.
        
        Args:
            query_embedding: Query embedding vector
            results: List of result dictionaries with embeddings
            k: Number of results to return
            embedding_key: Key for embedding in result dicts
            score_key: Optional key for initial relevance score
            
        Returns:
            Reordered list of results with diversity
        """
        if not results:
            return []
        
        if len(results) <= k:
            return results
        
        # Extract initial scores if available
        initial_scores = None
        if score_key:
            initial_scores = [r.get(score_key, 0.0) for r in results]
        
        # Run MMR diversification
        mmr_results = self.engine.diversify(
            query_embedding=query_embedding,
            candidates=results,
            get_embedding_fn=lambda r: np.array(r[embedding_key]),
            k=k,
            initial_scores=initial_scores
        )
        
        # Return reordered results
        return [r.document for r in mmr_results]
    
    def get_diverse_indices(
        self,
        query_embedding: np.ndarray,
        embeddings: List[np.ndarray],
        k: int = 5,
        initial_scores: Optional[List[float]] = None
    ) -> List[int]:
        """Get indices of diverse items without reordering.
        
        Args:
            query_embedding: Query embedding vector
            embeddings: List of candidate embeddings
            k: Number of items to select
            initial_scores: Optional initial relevance scores
            
        Returns:
            List of selected indices
        """
        results = self.engine.diversify_vectors(
            query_embedding=query_embedding,
            candidate_embeddings=embeddings,
            k=k,
            initial_scores=initial_scores
        )
        return [idx for idx, _ in results]


def create_mmr_engine(
    lambda_param: Optional[float] = None,
    config = None
) -> MMREngine:
    """Create an MMR engine with configuration.
    
    Args:
        lambda_param: Optional override for lambda parameter
        config: Optional configuration object
        
    Returns:
        Configured MMREngine instance
    """
    if config is None:
        config = get_config()
    
    if lambda_param is None:
        lambda_param = getattr(config.retrieval, 'mmr_lambda', 0.5)
    
    return MMREngine(lambda_param=lambda_param)
