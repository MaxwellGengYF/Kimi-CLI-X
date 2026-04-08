"""skill_rag: RAG pipeline using ChromaDB with simple hash-based embeddings.

This module provides a complete RAG (Retrieval-Augmented Generation) pipeline
that uses ChromaDB for vector storage and retrieval, with simple hash-based
embeddings that don't require external ML models.

Example:
    >>> from skill_rag import RAGPipeline
    >>> 
    >>> # Create pipeline
    >>> pipeline = RAGPipeline(
    ...     collection_name="my_docs",
    ...     persist_directory="./chroma_db"
    ... )
    >>> 
    >>> # Index documents
    >>> from pathlib import Path
    >>> result = pipeline.index_directory(Path("./docs"))
    >>> print(f"Indexed {result.new_chunks} new chunks")
    >>> 
    >>> # Query
    >>> results = pipeline.query("What is RAG?", top_k=3)
    >>> for r in results:
    ...     print(f"Score: {1-r.distance:.3f}, Content: {r.content[:100]}...")
"""

__version__ = "0.1.0"

# Main pipeline
from skill_rag.pipeline import RAGPipeline, QueryResult, IndexingResult

# Embeddings - simple hash-based only
from skill_rag.embeddings import SimpleEmbedder, EmbeddingService

# Vector store
from skill_rag.vector_store import ChromaVectorStore

# Document loader
from skill_rag.loader import Document, MarkdownLoader, UniversalDocumentLoader

# Hybrid search
from skill_rag.hybrid_search import (
    HybridSearcher,
    BM25Searcher,
    SearchResult,
    hybrid_query
)

# Query optimizer
from skill_rag.query_optimizer import QueryOptimizer, create_optimizer

# File tracking
from skill_rag.file_tracker import FileTracker, compute_file_hash

# Config
from skill_rag.config import RAGConfig, get_config, configure

__all__ = [
    # Version
    "__version__",
    # Pipeline
    "RAGPipeline",
    "QueryResult",
    "IndexingResult",
    # Embeddings
    "SimpleEmbedder",
    "EmbeddingService",
    # Vector store
    "ChromaVectorStore",
    # Loader
    "Document",
    "MarkdownLoader",
    "UniversalDocumentLoader",
    # Search
    "HybridSearcher",
    "BM25Searcher",
    "SearchResult",
    "hybrid_query",
    # Query optimizer
    "QueryOptimizer",
    "create_optimizer",
    # File tracking
    "FileTracker",
    "compute_file_hash",
    # Config
    "RAGConfig",
    "get_config",
    "configure",
]
