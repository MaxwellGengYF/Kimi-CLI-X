"""RAG (Retrieval-Augmented Generation) package.

This package provides offline-only RAG capabilities with:
- Local embedding models (sentence-transformers)
- Persistent vector storage (ChromaDB)
- Multiple retrievers (Dense, BM25, Hybrid, GraphRAG, AST-Aware)
- Configuration management for offline operation
"""

from typing import Optional

from .config import (
    RAGConfig,
    ConfigManager,
    EmbeddingConfig,
    StorageConfig,
    RetrieverConfig,
    OrchestratorConfig,
    OfflineValidationConfig,
    LoggingConfig,
    create_default_config_file,
    get_preset_config,
)
from .orchestrator import (
    RAGOrchestrator,
    QueryType,
    RAGResult,
    RetrievalConfig,
    IndexingPipeline,
)
from .store import BaseDocumentStore, Document, ChromaDocumentStore
from .embeddings import (
    BaseEmbeddingModel,
    SentenceTransformerEmbedding,
    MiniLMEmbedding,
    MPNetEmbedding,
)
from .retrievers import (
    BaseRetriever,
    RetrievedDocument,
    DenseRetriever,
    BM25Retriever,
    HybridRetriever,
    GraphRAGRetriever,
    ASTAwareRetriever,
)

def create_rag_orchestrator(
    config: Optional[RAGConfig] = None,
    preset: Optional[str] = None,
) -> "RAGOrchestrator":
    """
    Create a RAG orchestrator from configuration.
    
    Args:
        config: RAGConfig instance (uses default if None)
        preset: Preset name ('minimal', 'performance', 'privacy') - ignored if config provided
        
    Returns:
        Configured RAGOrchestrator instance
        
    Example:
        >>> from rag import create_rag_orchestrator, get_preset_config
        >>> # Using default config
        >>> orchestrator = create_rag_orchestrator()
        >>> # Using preset
        >>> orchestrator = create_rag_orchestrator(preset='performance')
        >>> # Using custom config
        >>> config = get_preset_config('privacy')
        >>> config.data_directory = './my_data'
        >>> orchestrator = create_rag_orchestrator(config)
    """
    from .embeddings import SentenceTransformerEmbedding
    from .retrievers import DenseRetriever, BM25Retriever, HybridRetriever
    from .store import ChromaDocumentStore
    
    # Get configuration
    if config is None:
        if preset:
            config = get_preset_config(preset)
        else:
            config = RAGConfig()
    
    # Apply logging config
    config.apply_logging_config()
    
    # Create embedding model with offline settings
    embedding_model = SentenceTransformerEmbedding(
        model_name=config.embedding.model_name,
        device=config.embedding.device,
        normalize_embeddings=config.embedding.normalize_embeddings,
        batch_size=config.embedding.batch_size,
        cache_folder=config.embedding.cache_dir,
        local_files_only=config.embedding.local_files_only,
    )
    
    # Create document store
    doc_store = ChromaDocumentStore(
        collection_name=config.storage.collection_name,
        persist_directory=config.storage.persist_directory,
        distance_metric=config.storage.distance_metric,
    )
    
    # Create retrievers
    dense_retriever = DenseRetriever(
        store=doc_store,
        embedding_model=embedding_model,
        top_k=config.retriever.dense_top_k,
        score_threshold=config.retriever.dense_score_threshold,
    )
    
    bm25_retriever = BM25Retriever(
        k1=config.retriever.bm25_k1,
        b=config.retriever.bm25_b,
        top_k=config.retriever.bm25_top_k,
    )
    
    hybrid_retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
        fusion_method=config.retriever.hybrid_fusion_method,
        rrf_k=config.retriever.hybrid_rrf_k,
        dense_weight=config.retriever.hybrid_dense_weight,
        bm25_weight=config.retriever.hybrid_bm25_weight,
        top_k=config.retriever.dense_top_k,
    )
    
    # Create orchestrator
    orchestrator = RAGOrchestrator(
        fusion_method=config.orchestrator.fusion_method,
        enable_query_classification=config.orchestrator.enable_query_classification,
        enable_cache=config.orchestrator.enable_cache,
        cache_size=config.orchestrator.cache_size,
    )
    
    # Register retrievers
    orchestrator.add_retriever(
        name="dense",
        retriever=dense_retriever,
        query_types=[QueryType.SEMANTIC, QueryType.HYBRID],
        weight=1.0,
        priority=3,
    )
    orchestrator.add_retriever(
        name="bm25",
        retriever=bm25_retriever,
        query_types=[QueryType.KEYWORD, QueryType.HYBRID],
        weight=0.8,
        priority=4,
    )
    orchestrator.add_retriever(
        name="hybrid",
        retriever=hybrid_retriever,
        query_types=[QueryType.HYBRID, QueryType.FACTUAL],
        weight=1.2,
        priority=2,
    )
    
    return orchestrator


__all__ = [
    # Configuration
    "RAGConfig",
    "ConfigManager",
    "EmbeddingConfig",
    "StorageConfig",
    "RetrieverConfig",
    "OrchestratorConfig",
    "OfflineValidationConfig",
    "LoggingConfig",
    "create_default_config_file",
    "get_preset_config",
    # Factory
    "create_rag_orchestrator",
    # Orchestrator
    "RAGOrchestrator",
    "QueryType",
    "RAGResult",
    "RetrievalConfig",
    "IndexingPipeline",
    # Store
    "BaseDocumentStore",
    "Document",
    "ChromaDocumentStore",
    # Embeddings
    "BaseEmbeddingModel",
    "SentenceTransformerEmbedding",
    "MiniLMEmbedding",
    "MPNetEmbedding",
    # Retrievers
    "BaseRetriever",
    "RetrievedDocument",
    "DenseRetriever",
    "BM25Retriever",
    "HybridRetriever",
    "GraphRAGRetriever",
    "ASTAwareRetriever",
]
