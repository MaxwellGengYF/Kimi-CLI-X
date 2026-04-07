"""Configuration management for RAG offline-only operation."""

import os
import json
import yaml
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """Configuration for embedding models (offline-only)."""
    
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: Optional[str] = None  # None = auto (cuda/cpu)
    normalize_embeddings: bool = False
    batch_size: int = 32
    trust_remote_code: bool = False
    
    # Local model cache
    cache_dir: Optional[str] = None
    local_files_only: bool = True  # Critical: never download from HuggingFace


@dataclass
class StorageConfig:
    """Configuration for document storage (offline-only)."""
    
    persist_directory: str = "./rag_storage"
    collection_name: str = "documents"
    distance_metric: str = "cosine"  # cosine, l2, ip
    
    # Anonymity settings
    anonymize_metadata: bool = False
    encryption_enabled: bool = False
    encryption_key_path: Optional[str] = None


@dataclass
class RetrieverConfig:
    """Configuration for retrievers."""
    
    # Dense retriever
    dense_top_k: int = 5
    dense_score_threshold: Optional[float] = None
    
    # BM25 retriever
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    bm25_top_k: int = 5
    
    # Hybrid retriever
    hybrid_fusion_method: str = "rrf"  # rrf, linear
    hybrid_rrf_k: int = 60
    hybrid_dense_weight: float = 0.5
    hybrid_bm25_weight: float = 0.5
    
    # GraphRAG retriever
    graph_max_depth: int = 2
    graph_vector_weight: float = 0.6
    graph_graph_weight: float = 0.4
    
    # AST-Aware retriever
    ast_structure_weight: float = 0.3
    ast_semantic_weight: float = 0.7


@dataclass
class OrchestratorConfig:
    """Configuration for RAG orchestrator."""
    
    default_query_type: str = "hybrid"
    fusion_method: str = "rrf"
    rrf_k: int = 60
    enable_query_classification: bool = True
    enable_cache: bool = True
    cache_size: int = 1000
    
    # Fallback behavior
    fallback_to_available: bool = True
    require_all_retrievers: bool = False


@dataclass
class OfflineValidationConfig:
    """Configuration for offline operation validation."""
    
    # Network restrictions
    block_network_calls: bool = True
    allow_localhost_only: bool = True
    
    # Model validation
    require_local_models: bool = True
    validate_model_checksums: bool = False
    allowed_model_sources: List[str] = field(default_factory=lambda: ["local", "cache"])
    
    # Storage validation
    require_local_storage: bool = True
    prohibit_cloud_storage: bool = True


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_to_file: bool = True
    log_file_path: Optional[str] = None
    log_queries: bool = False  # For privacy
    anonymize_logs: bool = True


@dataclass
class RAGConfig:
    """
    Complete configuration for RAG offline-only operation.
    
    This configuration ensures:
    - All models are loaded from local storage only
    - No network calls to external APIs
    - Persistent local storage for all data
    - Optional privacy features (anonymization, encryption)
    """
    
    # Component configurations
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    offline_validation: OfflineValidationConfig = field(default_factory=OfflineValidationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # Global settings
    version: str = "1.0.0"
    offline_mode: bool = True
    data_directory: str = "./rag_data"
    
    def __post_init__(self):
        """Post-initialization validation and setup."""
        # Ensure data directory exists
        os.makedirs(self.data_directory, exist_ok=True)
        
        # Set default storage path relative to data directory
        if not self.storage.persist_directory.startswith('/'):
            self.storage.persist_directory = os.path.join(
                self.data_directory, 
                self.storage.persist_directory
            )
        
        # Set default log file path
        if self.logging.log_to_file and not self.logging.log_file_path:
            self.logging.log_file_path = os.path.join(
                self.data_directory,
                "rag.log"
            )
        
        # Set default embedding cache dir
        if not self.embedding.cache_dir:
            self.embedding.cache_dir = os.path.join(
                self.data_directory,
                "models"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)
    
    def to_json(self, path: Optional[str] = None) -> str:
        """Export configuration to JSON."""
        json_str = json.dumps(self.to_dict(), indent=2)
        
        if path:
            with open(path, 'w') as f:
                f.write(json_str)
        
        return json_str
    
    def to_yaml(self, path: Optional[str] = None) -> str:
        """Export configuration to YAML."""
        yaml_str = yaml.dump(self.to_dict(), default_flow_style=False)
        
        if path:
            with open(path, 'w') as f:
                f.write(yaml_str)
        
        return yaml_str
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'RAGConfig':
        """Load configuration from dictionary."""
        # Extract nested configs
        embedding = EmbeddingConfig(**config_dict.get('embedding', {}))
        storage = StorageConfig(**config_dict.get('storage', {}))
        retriever = RetrieverConfig(**config_dict.get('retriever', {}))
        orchestrator = OrchestratorConfig(**config_dict.get('orchestrator', {}))
        offline_validation = OfflineValidationConfig(**config_dict.get('offline_validation', {}))
        logging = LoggingConfig(**config_dict.get('logging', {}))
        
        return cls(
            embedding=embedding,
            storage=storage,
            retriever=retriever,
            orchestrator=orchestrator,
            offline_validation=offline_validation,
            logging=logging,
            version=config_dict.get('version', '1.0.0'),
            offline_mode=config_dict.get('offline_mode', True),
            data_directory=config_dict.get('data_directory', './rag_data')
        )
    
    @classmethod
    def from_json(cls, path: str) -> 'RAGConfig':
        """Load configuration from JSON file."""
        with open(path, 'r') as f:
            config_dict = json.load(f)
        return cls.from_dict(config_dict)
    
    @classmethod
    def from_yaml(cls, path: str) -> 'RAGConfig':
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            config_dict = yaml.safe_load(f)
        return cls.from_dict(config_dict)
    
    def validate_offline_mode(self) -> List[str]:
        """
        Validate that configuration enforces offline-only operation.
        
        Returns:
            List of validation warnings/errors
        """
        issues = []
        
        # Check embedding config
        if not self.embedding.local_files_only:
            issues.append("WARNING: embedding.local_files_only is False - may download models")
        
        if self.embedding.model_name.startswith('http'):
            issues.append("ERROR: embedding.model_name appears to be a URL")
        
        # Check storage config
        if self.offline_validation.prohibit_cloud_storage:
            cloud_indicators = ['s3://', 'gs://', 'azure://', 'https://', 'http://']
            for indicator in cloud_indicators:
                if indicator in self.storage.persist_directory:
                    issues.append(f"ERROR: storage.persist_directory contains cloud indicator: {indicator}")
        
        # Check offline validation
        if not self.offline_validation.block_network_calls:
            issues.append("WARNING: offline_validation.block_network_calls is False")
        
        if not self.offline_validation.require_local_models:
            issues.append("WARNING: offline_validation.require_local_models is False")
        
        return issues
    
    def apply_logging_config(self) -> None:
        """Apply logging configuration."""
        level = getattr(logging, self.logging.level.upper(), logging.INFO)
        
        handlers = [logging.StreamHandler()]
        
        if self.logging.log_to_file and self.logging.log_file_path:
            os.makedirs(os.path.dirname(self.logging.log_file_path), exist_ok=True)
            handlers.append(logging.FileHandler(self.logging.log_file_path))
        
        logging.basicConfig(
            level=level,
            format=self.logging.format,
            handlers=handlers
        )
        
        logger.info(f"RAG logging configured at level {self.logging.level}")


class ConfigManager:
    """
    Manager for RAG configuration with environment and profile support.
    
    Supports:
    - Environment variable overrides
    - Profile-based configurations
    - Default presets
    """
    
    # Configuration search paths
    CONFIG_PATHS = [
        './rag_config.yaml',
        './rag_config.json',
        './.rag/config.yaml',
        os.path.expanduser('~/.rag/config.yaml'),
        os.path.expanduser('~/.config/rag/config.yaml'),
    ]
    
    def __init__(self, config: Optional[RAGConfig] = None):
        """
        Initialize config manager.
        
        Args:
            config: Optional configuration (uses default if None)
        """
        self.config = config or RAGConfig()
        self._apply_environment_overrides()
    
    def _apply_environment_overrides(self) -> None:
        """Apply environment variable overrides."""
        env_mappings = {
            'RAG_DATA_DIR': ('data_directory', str),
            'RAG_OFFLINE_MODE': ('offline_mode', lambda x: x.lower() == 'true'),
            'RAG_EMBEDDING_MODEL': ('embedding.model_name', str),
            'RAG_EMBEDDING_DEVICE': ('embedding.device', str),
            'RAG_EMBEDDING_CACHE': ('embedding.cache_dir', str),
            'RAG_STORAGE_DIR': ('storage.persist_directory', str),
            'RAG_LOG_LEVEL': ('logging.level', str),
            'RAG_LOG_FILE': ('logging.log_file_path', str),
        }
        
        for env_var, (config_path, converter) in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                try:
                    converted = converter(value)
                    self._set_nested_attr(config_path, converted)
                    logger.info(f"Applied env override: {env_var}={value}")
                except Exception as e:
                    logger.warning(f"Failed to apply {env_var}: {e}")
    
    def _set_nested_attr(self, path: str, value: Any) -> None:
        """Set a nested attribute by dot-separated path."""
        parts = path.split('.')
        obj = self.config
        
        for part in parts[:-1]:
            obj = getattr(obj, part)
        
        setattr(obj, parts[-1], value)
    
    @classmethod
    def auto_load(cls) -> 'ConfigManager':
        """
        Automatically load configuration from standard locations.
        
        Returns:
            ConfigManager with loaded or default configuration
        """
        for path in cls.CONFIG_PATHS:
            if os.path.exists(path):
                try:
                    if path.endswith('.yaml') or path.endswith('.yml'):
                        config = RAGConfig.from_yaml(path)
                    else:
                        config = RAGConfig.from_json(path)
                    
                    logger.info(f"Loaded configuration from {path}")
                    return cls(config)
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
        
        logger.info("Using default configuration")
        return cls()
    
    def save(self, path: Optional[str] = None) -> None:
        """
        Save configuration to file.
        
        Args:
            path: Save path (default: first CONFIG_PATHS entry)
        """
        path = path or self.CONFIG_PATHS[0]
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        
        if path.endswith('.yaml') or path.endswith('.yml'):
            self.config.to_yaml(path)
        else:
            self.config.to_json(path)
        
        logger.info(f"Saved configuration to {path}")
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """Get embedding configuration as kwargs dict."""
        return {
            'model_name': self.config.embedding.model_name,
            'device': self.config.embedding.device,
            'normalize_embeddings': self.config.embedding.normalize_embeddings,
            'batch_size': self.config.embedding.batch_size,
            'cache_folder': self.config.embedding.cache_dir,
        }
    
    def get_storage_config(self) -> Dict[str, Any]:
        """Get storage configuration as kwargs dict."""
        return {
            'persist_directory': self.config.storage.persist_directory,
            'collection_name': self.config.storage.collection_name,
            'distance_metric': self.config.storage.distance_metric,
        }
    
    def validate(self) -> List[str]:
        """Validate configuration and return any issues."""
        return self.config.validate_offline_mode()


def create_default_config_file(path: str = "./rag_config.yaml") -> str:
    """
    Create a default configuration file.
    
    Args:
        path: Path for config file
        
    Returns:
        Path to created file
    """
    config = RAGConfig()
    config.to_yaml(path)
    return path


def get_preset_config(preset_name: str) -> RAGConfig:
    """
    Get a preset configuration.
    
    Args:
        preset_name: Name of preset ('minimal', 'performance', 'privacy')
        
    Returns:
        RAGConfig for the preset
    """
    presets = {
        'minimal': RAGConfig(
            embedding=EmbeddingConfig(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                batch_size=16,
            ),
            storage=StorageConfig(
                distance_metric="cosine",
            ),
            logging=LoggingConfig(
                level="WARNING",
                log_to_file=False,
            )
        ),
        'performance': RAGConfig(
            embedding=EmbeddingConfig(
                model_name="sentence-transformers/all-mpnet-base-v2",
                device="cuda",
                batch_size=64,
                normalize_embeddings=True,
            ),
            retriever=RetrieverConfig(
                dense_top_k=10,
                hybrid_fusion_method="rrf",
            ),
            orchestrator=OrchestratorConfig(
                enable_cache=True,
                cache_size=5000,
            ),
            logging=LoggingConfig(
                level="INFO",
            )
        ),
        'privacy': RAGConfig(
            storage=StorageConfig(
                anonymize_metadata=True,
                encryption_enabled=True,
            ),
            offline_validation=OfflineValidationConfig(
                block_network_calls=True,
                require_local_models=True,
                validate_model_checksums=True,
            ),
            logging=LoggingConfig(
                anonymize_logs=True,
                log_queries=False,
            )
        ),
    }
    
    if preset_name not in presets:
        raise ValueError(f"Unknown preset: {preset_name}. Available: {list(presets.keys())}")
    
    return presets[preset_name]
