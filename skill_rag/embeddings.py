"""Embedding service for text vectorization using sentence-transformers with fallback."""

from typing import List, Optional, Union
import hashlib
import logging
import numpy as np
import re

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings using Word2Vec/GloVe."""
    
    DEFAULT_DIMENSION = 384
    
    def __init__(self, dimension: int = 384):
        """Initialize embedding service.
        
        Args:
            dimension: Dimension of the embedding vectors.
                      Defaults to 384 for compatibility.
        """
        self._dimension = dimension
        self._model = None
        self._fallback_dim = 100  # GloVe model dimension
    
    def _get_model(self):
        """Lazy load the Word2Vec/GloVe model."""
        # if self._model is None:
        #     try:
        #         import gensim.downloader as api
        #         # Load a lightweight pre-trained GloVe model
        #         # 'glove-wiki-gigaword-100' is ~128MB, good balance of size vs quality
        #         self._model = api.load("glove-wiki-gigaword-100")
        #         self._fallback_dim = self._model.vector_size
        #     except ImportError:
        #         # Try to install gensim
        #         import subprocess
        #         import sys
        #         print("gensim not found, attempting to install...")
        #         try:
        #             subprocess.check_call([sys.executable, "-m", "pip", "install", "gensim"])
        #             # Try import again after installation
        #             import gensim.downloader as api
        #             self._model = api.load("glove-wiki-gigaword-100")
        #             self._fallback_dim = self._model.vector_size
        #             print("gensim installed successfully and model loaded.")
        #         except Exception as e:
        #             # Fallback: use a simple hash-based embedding without gensim
        #             print(f"Warning: gensim not available after install attempt ({e}), using hash-based embeddings")
        #             self._model = {}
        #             self._fallback_dim = 100
        #     except Exception as e:
        #         # Fallback: if download fails, use hash-based embeddings
        #         print(f"Warning: Could not load GloVe model: {e}")
        self._model = {}
        return self._model
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization.
        
        Args:
            text: Input text
            
        Returns:
            List of tokens
        """
        # Convert to lowercase and extract words
        text = text.lower()
        # Keep alphanumeric characters and spaces
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        # Split into tokens
        tokens = text.split()
        return tokens
    
    def _get_word_vectors(self, tokens: List[str]) -> List[np.ndarray]:
        """Get word vectors for a list of tokens.
        
        Uses deterministic MD5 hash instead of Python's built-in hash() to ensure
        consistent vectors across runs (Python 3.3+ randomizes hash by default).
        
        Args:
            tokens: List of word tokens
            
        Returns:
            List of word vectors
        """
        model = self._get_model()
        vectors = []
        
        if not model:
            # Hash-based fallback: generate deterministic vectors from token hash
            for token in tokens:
                # Use MD5 for deterministic hashing (Python's hash() is randomized)
                hash_val = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)
                np.random.seed(hash_val % (2**31))
                vectors.append(np.random.randn(self._fallback_dim).astype(np.float32))
        else:
            for token in tokens:
                if token in model:
                    vectors.append(model[token])
        
        return vectors
    
    def _pool_vectors(self, vectors: List[np.ndarray]) -> np.ndarray:
        """Pool word vectors to get sentence embedding.
        Uses mean pooling by default.
        
        Args:
            vectors: List of word vectors
            
        Returns:
            Pooled sentence vector
        """
        if not vectors:
            # Return zero vector if no words found
            return np.zeros(self._fallback_dim)
        
        # Mean pooling
        sentence_vector = np.mean(vectors, axis=0)
        
        # Normalize to unit length
        norm = np.linalg.norm(sentence_vector)
        if norm > 0:
            sentence_vector = sentence_vector / norm
        
        return sentence_vector
    
    def embed(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            batch_size: Batch size (ignored, kept for API compatibility)
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []
        
        # Ensure model is loaded
        self._get_model()
        
        embeddings = []
        for text in texts:
            # Clean text
            cleaned_text = self._clean_text(text)
            
            # Tokenize
            tokens = self._tokenize(cleaned_text)
            
            # Get word vectors
            word_vectors = self._get_word_vectors(tokens)
            
            # Pool to get sentence vector
            sentence_vector = self._pool_vectors(word_vectors)
            
            # Pad or truncate to target dimension
            if len(sentence_vector) < self._dimension:
                # Pad with zeros
                sentence_vector = np.pad(
                    sentence_vector, 
                    (0, self._dimension - len(sentence_vector))
                )
            elif len(sentence_vector) > self._dimension:
                # Truncate
                sentence_vector = sentence_vector[:self._dimension]
            
            embeddings.append(sentence_vector.tolist())
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text.
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector as list of floats
        """
        embeddings = self.embed([text])
        return embeddings[0] if embeddings else []
    
    def _clean_text(self, text: str) -> str:
        """Clean text for embedding.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Remove excessive whitespace but preserve structure
        lines = text.splitlines()
        lines = [line.strip() for line in lines]
        text = ' '.join(line for line in lines if line)
        
        # Limit length to avoid issues
        max_length = 10000
        if len(text) > max_length:
            text = text[:max_length]
        
        return text
    
    @property
    def dimension(self) -> int:
        """Get the embedding dimension.
        
        Returns:
            Size of embedding vectors
        """
        return self._dimension


class SentenceTransformerEmbedder:
    """High-quality embedding service using sentence-transformers."""
    
    # Default model: all-MiniLM-L6-v2 (384-dim, fast, good quality)
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    
    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        """Initialize sentence-transformer embedder.
        
        Args:
            model_name: Name of the sentence-transformer model to use.
                       Defaults to 'all-MiniLM-L6-v2' (384-dim).
            device: Device to run on ('cpu', 'cuda', or None for auto)
        """
        self._model_name = model_name or self.DEFAULT_MODEL
        self._device = device
        self._model = None
        self._dimension = None
        self._fallback_embedder = None
    
    def _get_model(self):
        """Lazy load the sentence-transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                
                logger.info(f"Loading sentence-transformer model: {self._model_name}")
                self._model = SentenceTransformer(self._model_name, device=self._device)
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(f"Model loaded successfully. Dimension: {self._dimension}")
            except ImportError:
                logger.warning(
                    "sentence-transformers not available. "
                    "Install with: pip install sentence-transformers"
                )
                self._init_fallback()
            except Exception as e:
                logger.error(f"Failed to load model {self._model_name}: {e}")
                self._init_fallback()
        return self._model
    
    def _init_fallback(self):
        """Initialize fallback embedder."""
        logger.warning("Using fallback EmbeddingService")
        self._fallback_embedder = EmbeddingService(dimension=384)
        self._dimension = self._fallback_embedder.dimension
        self._model = None
    
    def embed(self, texts: List[str], batch_size: int = 32, show_progress: bool = False) -> List[List[float]]:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            batch_size: Batch size for encoding
            show_progress: Whether to show progress bar
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []
        
        model = self._get_model()
        
        if model is None and self._fallback_embedder:
            # Use fallback
            return self._fallback_embedder.embed(texts, batch_size)
        
        # Clean texts
        cleaned_texts = [self._clean_text(t) for t in texts]
        
        # Generate embeddings using sentence-transformers
        embeddings = model.encode(
            cleaned_texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True
        )
        
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text.
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector as list of floats
        """
        embeddings = self.embed([text], batch_size=1)
        return embeddings[0] if embeddings else []
    
    def _clean_text(self, text: str) -> str:
        """Clean text for embedding.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Basic cleaning - sentence-transformers handles most preprocessing
        # Just limit length to avoid issues
        max_length = 10000
        if len(text) > max_length:
            text = text[:max_length]
        return text.strip()
    
    @property
    def dimension(self) -> int:
        """Get the embedding dimension.
        
        Returns:
            Size of embedding vectors
        """
        if self._dimension is None:
            # Force model loading
            self._get_model()
        return self._dimension or 384
    
    @property
    def model_name(self) -> str:
        """Get the model name.
        
        Returns:
            Name of the loaded model
        """
        return self._model_name


# Type alias for embedder interface
Embedder = Union[EmbeddingService, SentenceTransformerEmbedder]
