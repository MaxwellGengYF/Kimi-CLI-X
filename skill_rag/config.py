"""Configuration for skill_rag module.

This module provides configuration settings for the RAG pipeline.
Uses pydantic-settings for environment variable support.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class VectorStoreConfig(BaseSettings):
    """Vector store configuration."""
    
    model_config = {"env_prefix": "SKILL_RAG_VECTOR_"}
    
    persist_directory: str = "./chroma_db"
    collection_name: str = "skill_docs"
    embedding_dimension: int = 384
    distance_metric: str = "cosine"


class SearchConfig(BaseSettings):
    """Search configuration."""
    
    model_config = {"env_prefix": "SKILL_RAG_SEARCH_"}
    
    default_top_k: int = 5
    hybrid_alpha: float = 0.5  # 0=BM25 only, 1=vector only
    use_query_optimizer: bool = False
    optimizer_mode: str = "expansion"


class ChunkingConfig(BaseSettings):
    """Document chunking configuration."""
    
    model_config = {"env_prefix": "SKILL_RAG_CHUNK_"}
    
    chunk_size: int = 1500
    chunk_overlap: int = 100
    use_semantic_chunking: bool = False


class RAGConfig(BaseSettings):
    """Main RAG configuration."""
    
    model_config = {"env_prefix": "SKILL_RAG_"}
    
    vector: VectorStoreConfig = VectorStoreConfig()
    search: SearchConfig = SearchConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    enable_file_tracking: bool = True


# Global config instance
_config: Optional[RAGConfig] = None


def get_config() -> RAGConfig:
    """Get or create the global configuration.
    
    Returns:
        RAGConfig instance
    """
    global _config
    if _config is None:
        _config = RAGConfig()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None


def configure(
    persist_directory: Optional[str] = None,
    collection_name: Optional[str] = None,
    embedding_dimension: Optional[int] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    use_semantic_chunking: Optional[bool] = None,
    default_top_k: Optional[int] = None,
    hybrid_alpha: Optional[float] = None
) -> RAGConfig:
    """Configure the RAG pipeline with custom settings.
    
    Args:
        persist_directory: Directory for ChromaDB persistence
        collection_name: Name of the collection
        embedding_dimension: Dimension for embeddings (default: 384)
        chunk_size: Size of document chunks
        chunk_overlap: Overlap between chunks
        use_semantic_chunking: Use semantic boundaries for chunking
        default_top_k: Default number of results
        hybrid_alpha: Weight for hybrid search (0=BM25, 1=vector)
        
    Returns:
        Updated RAGConfig instance
    """
    global _config
    _config = RAGConfig()
    
    if persist_directory is not None:
        _config.vector.persist_directory = persist_directory
    if collection_name is not None:
        _config.vector.collection_name = collection_name
    if embedding_dimension is not None:
        _config.vector.embedding_dimension = embedding_dimension
    if chunk_size is not None:
        _config.chunking.chunk_size = chunk_size
    if chunk_overlap is not None:
        _config.chunking.chunk_overlap = chunk_overlap
    if use_semantic_chunking is not None:
        _config.chunking.use_semantic_chunking = use_semantic_chunking
    if default_top_k is not None:
        _config.search.default_top_k = default_top_k
    if hybrid_alpha is not None:
        _config.search.hybrid_alpha = hybrid_alpha
    
    return _config
