"""Configuration management for skill_rag using pydantic-settings.

Configuration is loaded from (in order of priority):
1. Environment variables (e.g., SKILL_RAG_CHUNK_SIZE=500)
2. .env file in current working directory
3. Default values defined in this module

Environment variable names are prefixed with SKILL_RAG_ by default.
"""

from typing import List, Optional, Literal
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingConfig(BaseSettings):
    """Embedding model configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_EMBEDDING_",
        extra="ignore"
    )
    
    model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Name of the sentence-transformer model to use"
    )
    device: Literal["cpu", "cuda", "mps"] = Field(
        default="cpu",
        description="Device to run embeddings on"
    )
    normalize: bool = Field(
        default=True,
        description="Whether to normalize embeddings"
    )
    batch_size: int = Field(
        default=32,
        description="Batch size for embedding generation",
        ge=1,
        le=256
    )
    
    @field_validator('batch_size')
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 256:
            return 256
        return v


class VectorStoreConfig(BaseSettings):
    """Vector store (ChromaDB) configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_VECTORSTORE_",
        extra="ignore"
    )
    
    persist_directory: Optional[str] = Field(
        default=None,
        description="Directory to persist ChromaDB data (None = in-memory)"
    )
    collection_name: str = Field(
        default="skill_rag",
        description="Name of the ChromaDB collection"
    )
    distance_function: Literal["cosine", "l2", "ip"] = Field(
        default="cosine",
        description="Distance function for similarity search"
    )
    
    @field_validator('collection_name')
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        # ChromaDB collection names must be alphanumeric, hyphens, or underscores
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Collection name must be alphanumeric with hyphens or underscores only")
        return v


class RerankerConfig(BaseSettings):
    """Reranker configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_RERANKER_",
        extra="ignore"
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether to enable reranking"
    )
    model_name: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Name of the cross-encoder model"
    )
    top_k: int = Field(
        default=10,
        description="Number of documents to rerank",
        ge=1
    )


class HybridSearchConfig(BaseSettings):
    """Hybrid search configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_HYBRID_",
        extra="ignore"
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether to enable hybrid search"
    )
    vector_weight: float = Field(
        default=0.7,
        description="Weight for vector search scores (0-1)",
        ge=0.0,
        le=1.0
    )
    keyword_weight: float = Field(
        default=0.3,
        description="Weight for keyword search scores (0-1)",
        ge=0.0,
        le=1.0
    )
    
    @field_validator('vector_weight', 'keyword_weight')
    @classmethod
    def validate_weights(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class QueryOptimizationConfig(BaseSettings):
    """Query optimization configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_QUERY_",
        extra="ignore"
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether to enable query optimization"
    )
    expansion_enabled: bool = Field(
        default=True,
        description="Whether to enable query expansion"
    )
    expansion_cache_size: int = Field(
        default=1000,
        description="Cache size for query expansions",
        ge=0
    )
    hyde_enabled: bool = Field(
        default=False,
        description="Whether to enable HyDE (Hypothetical Document Embedding)"
    )


class LoaderConfig(BaseSettings):
    """Document loader configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_LOADER_",
        extra="ignore"
    )
    
    chunk_size: int = Field(
        default=1000,
        description="Default chunk size for text splitting",
        ge=100
    )
    chunk_overlap: int = Field(
        default=100,
        description="Default chunk overlap for text splitting",
        ge=0
    )
    semantic_code_chunking: bool = Field(
        default=True,
        description="Use semantic chunking for code files"
    )


class FileTrackingConfig(BaseSettings):
    """File tracking (incremental indexing) configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_TRACKING_",
        extra="ignore"
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether to enable file tracking"
    )
    state_file: str = Field(
        default=".file_tracker_state.json",
        description="Name of the file tracking state file"
    )


class MMRConfig(BaseSettings):
    """Maximal Marginal Relevance (MMR) configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_MMR_",
        extra="ignore"
    )
    
    enabled: bool = Field(
        default=False,
        description="Whether to enable MMR result diversification"
    )
    lambda_param: float = Field(
        default=0.5,
        description="Trade-off between relevance (1.0) and diversity (0.0)",
        ge=0.0,
        le=1.0
    )
    candidates: int = Field(
        default=20,
        description="Number of candidates to consider for MMR",
        ge=5,
        le=100
    )


class RAGConfig(BaseSettings):
    """Main RAG pipeline configuration.
    
    Configuration is loaded from environment variables with the prefix
    SKILL_RAG_ (e.g., SKILL_RAG_CHUNK_SIZE=500).
    
    A .env file in the current working directory will also be loaded
    if it exists.
    
    Example .env file:
        SKILL_RAG_CHUNK_SIZE=500
        SKILL_RAG_EMBEDDING_MODEL_NAME=sentence-transformers/all-mpnet-base-v2
        SKILL_RAG_HYBRID_VECTOR_WEIGHT=0.8
    """
    
    model_config = SettingsConfigDict(
        env_prefix="SKILL_RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Sub-configurations
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    hybrid_search: HybridSearchConfig = Field(default_factory=HybridSearchConfig)
    query_optimization: QueryOptimizationConfig = Field(default_factory=QueryOptimizationConfig)
    loader: LoaderConfig = Field(default_factory=LoaderConfig)
    file_tracking: FileTrackingConfig = Field(default_factory=FileTrackingConfig)
    mmr: MMRConfig = Field(default_factory=MMRConfig)
    
    # General settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level"
    )
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            "embedding": self.embedding.model_dump(),
            "vector_store": self.vector_store.model_dump(),
            "reranker": self.reranker.model_dump(),
            "hybrid_search": self.hybrid_search.model_dump(),
            "query_optimization": self.query_optimization.model_dump(),
            "loader": self.loader.model_dump(),
            "file_tracking": self.file_tracking.model_dump(),
            "mmr": self.mmr.model_dump(),
            "log_level": self.log_level,
        }
    
    @classmethod
    def from_file(cls, path: Path) -> "RAGConfig":
        """Load configuration from a .env file.
        
        Args:
            path: Path to the .env file
            
        Returns:
            RAGConfig instance loaded from file
        """
        # Load the .env file content manually
        from dotenv import load_dotenv
        import os
        
        # Save current env
        original_env = dict(os.environ)
        
        try:
            # Clear relevant env vars to ensure fresh load
            for key in list(os.environ.keys()):
                if key.startswith('SKILL_RAG_'):
                    del os.environ[key]
            
            # Load .env file
            load_dotenv(path, override=True)
            
            # Create config - sub-configs will pick up env vars
            return cls()
        finally:
            # Restore original env (optional - we might want to keep the loaded values)
            pass
    
    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Load configuration from current environment variables.
        
        Returns:
            RAGConfig instance loaded from environment
        """
        return cls()


# Global configuration instance
_config: Optional[RAGConfig] = None


def get_config() -> RAGConfig:
    """Get the global configuration instance.
    
    Returns:
        RAGConfig instance (creates one if it doesn't exist)
    """
    global _config
    if _config is None:
        _config = RAGConfig()
    return _config


def set_config(config: RAGConfig) -> None:
    """Set the global configuration instance.
    
    Args:
        config: Configuration instance to use globally
    """
    global _config
    _config = config


def reload_config() -> RAGConfig:
    """Reload configuration from environment/file.
    
    Returns:
        New RAGConfig instance
    """
    global _config
    _config = RAGConfig()
    return _config


# Convenience accessors
def get_embedding_config() -> EmbeddingConfig:
    """Get embedding configuration."""
    return get_config().embedding


def get_vector_store_config() -> VectorStoreConfig:
    """Get vector store configuration."""
    return get_config().vector_store


def get_reranker_config() -> RerankerConfig:
    """Get reranker configuration."""
    return get_config().reranker


def get_hybrid_search_config() -> HybridSearchConfig:
    """Get hybrid search configuration."""
    return get_config().hybrid_search


def get_mmr_config() -> MMRConfig:
    """Get MMR configuration."""
    return get_config().mmr
