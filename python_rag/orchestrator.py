"""RAG Orchestrator to combine and manage all retrievers."""

import time
import hashlib
from typing import List, Dict, Any, Optional, Callable, Union, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from python_rag.store.base import Document, BaseDocumentStore
from python_rag.store.chroma_store import ChromaDocumentStore
from python_rag.embeddings.base import BaseEmbeddingModel
from python_rag.embeddings.sentence_transformer import MiniLMEmbedding

from python_rag.retrievers.base import BaseRetriever, RetrievedDocument
from python_rag.retrievers.dense import DenseRetriever
from python_rag.retrievers.bm25 import BM25Retriever
from python_rag.retrievers.hybrid import HybridRetriever
from python_rag.retrievers.graph_rag import GraphRAGRetriever
from python_rag.retrievers.ast_aware import ASTAwareRetriever


class QueryType(Enum):
    """Types of queries for routing to appropriate retrievers."""
    SEMANTIC = "semantic"           # Natural language, conceptual
    KEYWORD = "keyword"             # Exact terms, technical names
    HYBRID = "hybrid"               # Mixed semantic + keyword
    CODE_STRUCTURE = "code_structure"  # Code AST patterns
    CODE_RELATIONSHIP = "code_relationship"  # Code dependencies
    FACTUAL = "factual"             # Specific facts/data


@dataclass
class RetrievalConfig:
    """Configuration for a retriever in the orchestrator."""
    retriever: BaseRetriever
    name: str
    query_types: List[QueryType] = field(default_factory=list)
    weight: float = 1.0
    enabled: bool = True
    priority: int = 0  # Higher = earlier in order
    
    def __post_init__(self):
        if not self.query_types:
            self.query_types = [QueryType.HYBRID]


@dataclass
class RAGResult:
    """Result from RAG orchestration."""
    query: str
    documents: List[RetrievedDocument]
    query_type: QueryType
    sources: Dict[str, List[RetrievedDocument]]  # Per-retriever results
    total_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_context_string(self, max_length: int = 4000) -> str:
        """Convert results to context string for LLM."""
        parts = []
        current_length = 0
        
        for i, doc in enumerate(self.documents, start=1):
            entry = f"[{i}] {doc.document.content[:500]}\n"
            if current_length + len(entry) > max_length:
                break
            parts.append(entry)
            current_length += len(entry)
        
        return "\n".join(parts)


@dataclass
class IndexingPipeline:
    """Pipeline for indexing documents into retrievers."""
    name: str
    document_processor: Optional[Callable[[Document], Document]] = None
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: Optional[BaseEmbeddingModel] = None
    metadata_enricher: Optional[Callable[[Document], Dict]] = None


class RAGOrchestrator:
    """
    Orchestrates multiple retrievers for unified RAG operations.
    
    Features:
    - Query routing to appropriate retrievers
    - Multi-source retrieval with fusion
    - Configurable retrieval strategies
    - Pipeline-based indexing
    - Performance monitoring
    - Fallback handling
    """
    
    def __init__(
        self,
        default_query_type: QueryType = QueryType.HYBRID,
        fusion_method: str = "rrf",
        rrf_k: int = 60,
        enable_query_classification: bool = True,
        enable_cache: bool = False,
        cache_size: int = 1000
    ):
        """
        Initialize RAG orchestrator.
        
        Args:
            default_query_type: Default query type if classification disabled
            fusion_method: Method for combining results ('rrf', 'linear', 'priority')
            rrf_k: RRF constant for rank fusion
            enable_query_classification: Auto-detect query type
            enable_cache: Cache retrieval results
            cache_size: Maximum cache entries
        """
        self._retrievers: Dict[str, RetrievalConfig] = {}
        self._pipelines: Dict[str, IndexingPipeline] = {}
        self._document_store: Optional[BaseDocumentStore] = None
        
        self.default_query_type = default_query_type
        self.fusion_method = fusion_method
        self.rrf_k = rrf_k
        self.enable_query_classification = enable_query_classification
        
        self._query_classifier: Optional[Callable[[str], QueryType]] = None
        self._cache: Optional[Dict] = None
        self._cache_enabled = enable_cache
        if enable_cache:
            self._cache = {}
            self._cache_size = cache_size
        
        self._stats = {
            'total_queries': 0,
            'avg_latency_ms': 0,
            'cache_hits': 0,
            'retriever_usage': defaultdict(int)
        }
    
    # ==================== Retriever Management ====================
    
    def add_retriever(
        self,
        name: str,
        retriever: BaseRetriever,
        query_types: Optional[List[QueryType]] = None,
        weight: float = 1.0,
        priority: int = 0
    ) -> 'RAGOrchestrator':
        """
        Add a retriever to the orchestrator.
        
        Args:
            name: Unique retriever identifier
            retriever: Retriever instance
            query_types: Query types this retriever handles
            weight: Fusion weight for this retriever
            priority: Execution priority (higher = earlier)
            
        Returns:
            Self for chaining
        """
        config = RetrievalConfig(
            retriever=retriever,
            name=name,
            query_types=query_types or [QueryType.HYBRID],
            weight=weight,
            priority=priority
        )
        self._retrievers[name] = config
        logger.info(f"Added retriever '{name}' with types {query_types}")
        return self
    
    def remove_retriever(self, name: str) -> None:
        """Remove a retriever by name."""
        if name in self._retrievers:
            del self._retrievers[name]
            logger.info(f"Removed retriever '{name}'")
    
    def enable_retriever(self, name: str) -> None:
        """Enable a retriever."""
        if name in self._retrievers:
            self._retrievers[name].enabled = True
    
    def disable_retriever(self, name: str) -> None:
        """Disable a retriever."""
        if name in self._retrievers:
            self._retrievers[name].enabled = False
    
    def set_retriever_weight(self, name: str, weight: float) -> None:
        """Update retriever fusion weight."""
        if name in self._retrievers:
            self._retrievers[name].weight = weight
    
    def get_retrievers(
        self,
        query_type: Optional[QueryType] = None
    ) -> List[Tuple[str, BaseRetriever]]:
        """
        Get retrievers for a query type, sorted by priority.
        
        Args:
            query_type: Filter by query type
            
        Returns:
            List of (name, retriever) tuples
        """
        configs = self._retrievers.values()
        
        # Filter by enabled and query type
        filtered = [
            c for c in configs
            if c.enabled and (query_type is None or query_type in c.query_types)
        ]
        
        # Sort by priority (descending)
        filtered.sort(key=lambda c: c.priority, reverse=True)
        
        return [(c.name, c.retriever) for c in filtered]
    
    # ==================== Query Classification ====================
    
    def set_query_classifier(self, classifier: Callable[[str], QueryType]) -> None:
        """
        Set custom query classifier.
        
        Args:
            classifier: Function mapping query string to QueryType
        """
        self._query_classifier = classifier
    
    def classify_query(self, query: str) -> QueryType:
        """
        Classify query to determine best retrievers.
        
        Uses keyword heuristics:
        - CODE_STRUCTURE: AST-related keywords (function, class, method)
        - CODE_RELATIONSHIP: dependency keywords (calls, imports, extends)
        - KEYWORD: exact term patterns, identifiers
        - SEMANTIC: natural language questions
        - HYBRID: mixed patterns
        """
        if self._query_classifier:
            return self._query_classifier(query)
        
        query_lower = query.lower()
        
        # Code relationship indicators (check first - queries like "what calls this function"
        # contain both relationship and structure keywords, so prioritize relationship)
        relationship_keywords = [
            'calls', 'imports', 'depends', 'inherits', 'extends',
            'implements', 'uses', 'relationship', 'dependency'
        ]
        if any(kw in query_lower for kw in relationship_keywords):
            return QueryType.CODE_RELATIONSHIP
        
        # Code structure indicators
        code_structure_keywords = [
            'function', 'def ', 'class ', 'method', 'async',
            'decorator', 'inheritance', 'try-except', 'control flow'
        ]
        if any(kw in query_lower for kw in code_structure_keywords):
            return QueryType.CODE_STRUCTURE
        
        # Keyword indicators (exact terms, identifiers)
        if self._looks_like_keyword_query(query):
            return QueryType.KEYWORD
        
        # Factual question indicators
        factual_patterns = [
            'what is', 'how to', 'how do', 'what are',
            'define', 'explain', 'difference between'
        ]
        if any(p in query_lower for p in factual_patterns):
            return QueryType.SEMANTIC
        
        return self.default_query_type
    
    def _looks_like_keyword_query(self, query: str) -> bool:
        """Check if query looks like keyword search."""
        # Contains code identifiers, camelCase, snake_case
        import re
        
        # Contains CamelCase or snake_case patterns
        if re.search(r'\b[a-z]+_[a-z]+\b', query):  # snake_case
            return True
        if re.search(r'\b[A-Z][a-z]+[A-Z]', query):  # CamelCase
            return True
        
        # Short, specific terms
        if len(query.split()) <= 3 and not query.endswith('?'):
            return True
        
        return False
    
    # ==================== Retrieval ====================
    
    def retrieve(
        self,
        query: str,
        query_type: Optional[QueryType] = None,
        top_k: int = 5,
        use_cache: bool = True,
        filter_fn: Optional[Callable[[Document], bool]] = None
    ) -> RAGResult:
        """
        Retrieve documents using orchestrated retrievers.
        
        Args:
            query: Search query
            query_type: Force specific query type (or auto-detect)
            top_k: Number of results to return
            use_cache: Use result cache
            filter_fn: Additional document filter
            
        Returns:
            RAGResult with fused documents
        """
        start_time = time.time()
        
        # Check cache
        cache_key = self._make_cache_key(query, query_type, top_k)
        if use_cache and self._cache_enabled and cache_key in self._cache:
            self._stats['cache_hits'] += 1
            return self._cache[cache_key]
        
        # Classify query
        if query_type is None:
            query_type = self.classify_query(query) if self.enable_query_classification else self.default_query_type
        
        logger.info(f"Query: '{query[:50]}...' | Type: {query_type.value}")
        
        # Get retrievers for this query type
        retrievers = self.get_retrievers(query_type)
        
        if not retrievers:
            # Fall back to all enabled retrievers
            retrievers = [
                (name, c.retriever)
                for name, c in self._retrievers.items()
                if c.enabled
            ]
        
        # Retrieve from all relevant retrievers
        all_results: Dict[str, List[RetrievedDocument]] = {}
        
        for name, retriever in retrievers:
            try:
                results = retriever.retrieve(query)
                if results:
                    all_results[name] = results
                    self._stats['retriever_usage'][name] += 1
            except Exception as e:
                logger.warning(f"Retriever '{name}' failed: {e}")
        
        # Fuse results
        if len(all_results) == 1:
            # Single source, no fusion needed
            fused_results = list(all_results.values())[0][:top_k]
        elif len(all_results) > 1:
            # Fuse multiple sources
            fused_results = self._fuse_results(all_results, top_k)
        else:
            # No results
            fused_results = []
        
        # Apply custom filter
        if filter_fn:
            fused_results = [r for r in fused_results if filter_fn(r.document)]
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Update stats
        self._update_stats(elapsed_ms)
        
        result = RAGResult(
            query=query,
            documents=fused_results,
            query_type=query_type,
            sources=all_results,
            total_time_ms=elapsed_ms,
            metadata={
                'retrievers_used': list(all_results.keys()),
                'result_count': len(fused_results)
            }
        )
        
        # Cache result
        if use_cache and self._cache_enabled:
            self._cache[cache_key] = result
            self._trim_cache()
        
        return result
    
    def batch_retrieve(
        self,
        queries: List[str],
        query_type: Optional[QueryType] = None,
        top_k: int = 5
    ) -> List[RAGResult]:
        """
        Retrieve for multiple queries.
        
        Args:
            queries: List of queries
            query_type: Query type for all (or auto-detect per query)
            top_k: Results per query
            
        Returns:
            List of RAGResults
        """
        return [
            self.retrieve(q, query_type=query_type, top_k=top_k)
            for q in queries
        ]
    
    def _fuse_results(
        self,
        results: Dict[str, List[RetrievedDocument]],
        top_k: int
    ) -> List[RetrievedDocument]:
        """
        Fuse results from multiple retrievers.
        
        Args:
            results: Dict of retriever_name -> documents
            top_k: Number of results to return
            
        Returns:
            Fused and ranked results
        """
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(results, top_k)
        elif self.fusion_method == "linear":
            return self._linear_fusion(results, top_k)
        elif self.fusion_method == "priority":
            return self._priority_fusion(results, top_k)
        else:
            raise ValueError(f"Unknown fusion method: {self.fusion_method}")
    
    def _reciprocal_rank_fusion(
        self,
        results: Dict[str, List[RetrievedDocument]],
        top_k: int
    ) -> List[RetrievedDocument]:
        """RRF: Reciprocal Rank Fusion."""
        scores: Dict[str, float] = defaultdict(float)
        docs: Dict[str, Document] = {}
        
        for name, retriever_results in results.items():
            weight = self._retrievers[name].weight
            
            for rank, result in enumerate(retriever_results, start=1):
                doc_id = result.document.id
                scores[doc_id] += weight * (1.0 / (self.rrf_k + rank))
                if doc_id not in docs:
                    docs[doc_id] = result.document
        
        # Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Create RetrievedDocument objects
        fused = []
        for rank, doc_id in enumerate(sorted_ids[:top_k], start=1):
            fused.append(RetrievedDocument(
                document=docs[doc_id],
                score=scores[doc_id],
                rank=rank
            ))
        
        return fused
    
    def _linear_fusion(
        self,
        results: Dict[str, List[RetrievedDocument]],
        top_k: int
    ) -> List[RetrievedDocument]:
        """Linear score fusion with normalization."""
        scores: Dict[str, float] = defaultdict(float)
        docs: Dict[str, Document] = {}
        
        for name, retriever_results in results.items():
            weight = self._retrievers[name].weight
            
            if not retriever_results:
                continue
            
            # Normalize scores
            max_score = max(r.score for r in retriever_results)
            min_score = min(r.score for r in retriever_results)
            score_range = max_score - min_score if max_score > min_score else 1
            
            for result in retriever_results:
                doc_id = result.document.id
                normalized = (result.score - min_score) / score_range
                scores[doc_id] += weight * normalized
                if doc_id not in docs:
                    docs[doc_id] = result.document
        
        # Sort and return
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        fused = []
        for rank, doc_id in enumerate(sorted_ids[:top_k], start=1):
            fused.append(RetrievedDocument(
                document=docs[doc_id],
                score=scores[doc_id],
                rank=rank
            ))
        
        return fused
    
    def _priority_fusion(
        self,
        results: Dict[str, List[RetrievedDocument]],
        top_k: int
    ) -> List[RetrievedDocument]:
        """Priority fusion: use highest priority retriever results first."""
        # Sort retrievers by priority
        sorted_configs = sorted(
            self._retrievers.values(),
            key=lambda c: c.priority,
            reverse=True
        )
        
        seen_ids: Set[str] = set()
        fused: List[RetrievedDocument] = []
        
        for config in sorted_configs:
            if config.name not in results:
                continue
            
            for result in results[config.name]:
                if result.document.id not in seen_ids:
                    seen_ids.add(result.document.id)
                    fused.append(result)
                    
                    if len(fused) >= top_k:
                        # Re-rank
                        for i, r in enumerate(fused, start=1):
                            r.rank = i
                        return fused
        
        # Re-rank final results
        for i, r in enumerate(fused, start=1):
            r.rank = i
        
        return fused
    
    # ==================== Indexing ====================
    
    def add_documents(
        self,
        documents: List[Document],
        pipeline: Optional[str] = None
    ) -> None:
        """
        Add documents to all compatible retrievers.
        
        Args:
            documents: Documents to index
            pipeline: Optional pipeline name for preprocessing
        """
        # Apply pipeline if specified
        if pipeline and pipeline in self._pipelines:
            documents = self._apply_pipeline(documents, self._pipelines[pipeline])
        
        # Add to each retriever
        for name, config in self._retrievers.items():
            if not config.enabled:
                continue
            
            try:
                retriever = config.retriever
                
                # Route to appropriate method based on retriever type
                if isinstance(retriever, DenseRetriever):
                    retriever.add_documents(documents)
                    logger.info(f"Indexed {len(documents)} docs to DenseRetriever '{name}'")
                    
                elif isinstance(retriever, BM25Retriever):
                    retriever.add_documents(documents)
                    logger.info(f"Indexed {len(documents)} docs to BM25Retriever '{name}'")
                    
                elif isinstance(retriever, ASTAwareRetriever):
                    for doc in documents:
                        retriever.add_code(
                            doc.content,
                            doc.metadata.get('file_path', doc.id),
                            doc.metadata
                        )
                    logger.info(f"Indexed {len(documents)} docs to ASTAwareRetriever '{name}'")
                    
                elif isinstance(retriever, GraphRAGRetriever):
                    files = [
                        (doc.metadata.get('file_path', doc.id), doc.content)
                        for doc in documents
                    ]
                    retriever.add_code_files(files)
                    logger.info(f"Indexed {len(documents)} files to GraphRAGRetriever '{name}'")
                    
                elif isinstance(retriever, HybridRetriever):
                    # Hybrid manages its own retrievers
                    pass
                else:
                    # Try generic add_documents method
                    if hasattr(retriever, 'add_documents'):
                        retriever.add_documents(documents)
                        logger.info(f"Indexed {len(documents)} docs to '{name}'")
                    
            except Exception as e:
                logger.warning(f"Failed to index to '{name}': {e}")
    
    def add_code_files(
        self,
        files: List[Tuple[str, str]],
        language: str = "python"
    ) -> None:
        """
        Add code files to code-aware retrievers.
        
        Args:
            files: List of (file_path, content) tuples
            language: Programming language
        """
        for name, config in self._retrievers.items():
            if not config.enabled:
                continue
            
            try:
                retriever = config.retriever
                
                if isinstance(retriever, ASTAwareRetriever):
                    for path, content in files:
                        retriever.add_code(content, path)
                    logger.info(f"Indexed {len(files)} files to ASTAwareRetriever '{name}'")
                    
                elif isinstance(retriever, GraphRAGRetriever):
                    retriever.add_code_files(files)
                    logger.info(f"Indexed {len(files)} files to GraphRAGRetriever '{name}'")
                    
            except Exception as e:
                logger.warning(f"Failed to index code to '{name}': {e}")
    
    def _apply_pipeline(
        self,
        documents: List[Document],
        pipeline: IndexingPipeline
    ) -> List[Document]:
        """Apply indexing pipeline to documents."""
        processed = []
        
        for doc in documents:
            # Custom processor
            if pipeline.document_processor:
                doc = pipeline.document_processor(doc)
            
            # Chunk if needed
            if len(doc.content) > pipeline.chunk_size:
                chunks = self._chunk_document(doc, pipeline.chunk_size, pipeline.chunk_overlap)
                processed.extend(chunks)
            else:
                processed.append(doc)
        
        return processed
    
    def _chunk_document(
        self,
        document: Document,
        chunk_size: int,
        chunk_overlap: int
    ) -> List[Document]:
        """Split document into chunks."""
        content = document.content
        chunks = []
        
        start = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            
            # Try to break at paragraph or sentence
            if end < len(content):
                # Look for paragraph break
                para_break = content.rfind('\n\n', start, end)
                if para_break > start + chunk_size // 2:
                    end = para_break + 2
                else:
                    # Look for sentence break
                    sent_break = content.rfind('. ', start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + 2
            
            chunk_content = content[start:end].strip()
            if chunk_content:
                chunk_id = f"{document.id}_chunk_{len(chunks)}"
                chunk = Document(
                    id=chunk_id,
                    content=chunk_content,
                    metadata={
                        **document.metadata,
                        'parent_id': document.id,
                        'chunk_index': len(chunks),
                        'chunk_start': start,
                        'chunk_end': end
                    }
                )
                chunks.append(chunk)
            
            start = end - chunk_overlap
            if start >= end:
                break
        
        return chunks
    
    # ==================== Pipeline Management ====================
    
    def add_pipeline(self, name: str, pipeline: IndexingPipeline) -> None:
        """Add an indexing pipeline."""
        self._pipelines[name] = pipeline
    
    def remove_pipeline(self, name: str) -> None:
        """Remove a pipeline."""
        if name in self._pipelines:
            del self._pipelines[name]
    
    # ==================== Statistics ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            **self._stats,
            'retriever_count': len(self._retrievers),
            'enabled_retrievers': sum(1 for c in self._retrievers.values() if c.enabled),
            'cache_size': len(self._cache) if self._cache else 0
        }
    
    def _update_stats(self, latency_ms: float) -> None:
        """Update performance statistics."""
        self._stats['total_queries'] += 1
        
        # Rolling average
        n = self._stats['total_queries']
        self._stats['avg_latency_ms'] = (
            (self._stats['avg_latency_ms'] * (n - 1) + latency_ms) / n
        )
    
    def clear_cache(self) -> None:
        """Clear result cache."""
        if self._cache:
            self._cache.clear()
    
    def _make_cache_key(
        self,
        query: str,
        query_type: Optional[QueryType],
        top_k: int
    ) -> str:
        """Generate cache key."""
        key_str = f"{query}:{query_type}:{top_k}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _trim_cache(self) -> None:
        """Trim cache to size limit."""
        if not self._cache:
            return
        
        if len(self._cache) > self._cache_size:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(self._cache.keys())[:-self._cache_size]
            for key in keys_to_remove:
                del self._cache[key]
    
    # ==================== Factory Methods ====================
    
    @classmethod
    def create_default(
        cls,
        persist_directory: Optional[str] = None,
        embedding_model: Optional[BaseEmbeddingModel] = None
    ) -> 'RAGOrchestrator':
        """
        Create default orchestrator with common retrievers.
        
        Args:
            persist_directory: Directory for persistence
            embedding_model: Embedding model (defaults to MiniLM)
            
        Returns:
            Configured RAGOrchestrator
        """
        embedding_model = embedding_model or MiniLMEmbedding()
        
        # Create store
        store = ChromaDocumentStore(
            collection_name="default",
            persist_directory=persist_directory,
            embedding_function=None  # We provide embeddings manually
        )
        
        # Create retrievers
        dense = DenseRetriever(store=store, embedding_model=embedding_model)
        bm25 = BM25Retriever()
        hybrid = HybridRetriever(dense_retriever=dense, bm25_retriever=bm25)
        ast_aware = ASTAwareRetriever(embedding_model=embedding_model)
        graph_rag = GraphRAGRetriever(embedding_model=embedding_model)
        
        # Create orchestrator
        orchestrator = cls(
            fusion_method="rrf",
            enable_query_classification=True,
            enable_cache=True
        )
        
        # Add retrievers with type routing
        orchestrator.add_retriever(
            "hybrid",
            hybrid,
            query_types=[QueryType.HYBRID, QueryType.SEMANTIC, QueryType.KEYWORD],
            weight=1.0,
            priority=10
        )
        orchestrator.add_retriever(
            "ast",
            ast_aware,
            query_types=[QueryType.CODE_STRUCTURE],
            weight=1.0,
            priority=8
        )
        orchestrator.add_retriever(
            "graph",
            graph_rag,
            query_types=[QueryType.CODE_RELATIONSHIP],
            weight=1.0,
            priority=7
        )
        
        return orchestrator
