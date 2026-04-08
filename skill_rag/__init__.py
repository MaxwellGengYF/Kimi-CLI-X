"""RAG (Retrieval-Augmented Generation) system with ChromaDB."""

# Document loading
from skill_rag.document_loaders import (
    Document,
    BaseLoader,
    MarkdownLoader,
    TextLoader,
    PDFLoader,
    WordLoader,
    AutoLoader,
    get_loader_for_file
)

# Backward compatibility alias
UniversalDocumentLoader = AutoLoader

# Configuration
from skill_rag.config import (
    RAGConfig,
    EmbeddingConfig,
    VectorStoreConfig,
    RerankerConfig,
    HybridSearchConfig,
    QueryOptimizationConfig,
    LoaderConfig,
    FileTrackingConfig,
    MMRConfig,
    get_config,
    set_config,
    reload_config,
    get_embedding_config,
    get_vector_store_config,
    get_reranker_config,
    get_hybrid_search_config,
    get_mmr_config,
)

# Code loading
from skill_rag.code_loader import (
    CodeLoader,
    CodeBlock,
    LanguageParser,
    PythonParser,
    JavaScriptParser,
    GenericCodeParser,
    get_parser,
    is_code_file,
    create_code_loader
)

# Embeddings
from skill_rag.embeddings import EmbeddingService, SentenceTransformerEmbedder
from skill_rag.embedding_cache import (
    EmbeddingCache,
    CachedEmbedder,
    cached_embedder
)

# Vector store
from skill_rag.vector_store import ChromaVectorStore

# Reranker
from skill_rag.reranker import Reranker, CrossEncoderReranker

# Hybrid search
from skill_rag.hybrid_search import HybridSearcher, HybridSearchResult

# Query optimization
from skill_rag.query_optimizer import (
    QueryOptimizer,
    QueryExpander,
    HyDEGenerator,
    OptimizedQuery,
    create_optimizer
)

# File tracking (incremental indexing)
from skill_rag.file_tracker import FileTracker, compute_file_hash

# MMR Diversity
from skill_rag.mmr_diversity import (
    MMREngine,
    MMRDiversifier,
    MMRResult,
    create_mmr_engine,
    cosine_similarity
)

# Main pipeline
from skill_rag.pipeline import RAGPipeline, QueryResult, IndexingResult

__version__ = "0.3.0"
__all__ = [
    # Document loading
    "Document",
    "BaseLoader",
    "MarkdownLoader",
    "TextLoader",
    "PDFLoader",
    "WordLoader",
    "AutoLoader",
    "get_loader_for_file",
    # Code loading
    "CodeLoader",
    "CodeBlock",
    "LanguageParser",
    "PythonParser",
    "JavaScriptParser",
    "GenericCodeParser",
    "get_parser",
    "is_code_file",
    "create_code_loader",
    # Embeddings
    "EmbeddingService",
    "SentenceTransformerEmbedder",
    "EmbeddingCache",
    "CachedEmbedder",
    "cached_embedder",
    # Vector store
    "ChromaVectorStore",
    # Reranker
    "Reranker",
    "CrossEncoderReranker",
    # Hybrid search
    "HybridSearcher",
    "HybridSearchResult",
    # Query optimization
    "QueryOptimizer",
    "QueryExpander",
    "HyDEGenerator",
    "OptimizedQuery",
    "create_optimizer",
    # File tracking
    "FileTracker",
    "compute_file_hash",
    # MMR Diversity
    "MMREngine",
    "MMRDiversifier",
    "MMRResult",
    "create_mmr_engine",
    "cosine_similarity",
    # Pipeline
    "RAGPipeline",
    "QueryResult",
    "IndexingResult",
    # Configuration
    "RAGConfig",
    "EmbeddingConfig",
    "VectorStoreConfig",
    "RerankerConfig",
    "HybridSearchConfig",
    "QueryOptimizationConfig",
    "LoaderConfig",
    "FileTrackingConfig",
    "MMRConfig",
    "get_config",
    "set_config",
    "reload_config",
    "get_embedding_config",
    "get_vector_store_config",
    "get_reranker_config",
    "get_hybrid_search_config",
    "get_mmr_config",
]
