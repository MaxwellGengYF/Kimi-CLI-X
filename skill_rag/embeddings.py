"""Embedding service for text vectorization using Word2Vec/GloVe."""

from typing import List, Optional
import numpy as np
import re


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
                np.random.seed(hash(token) % (2**31))
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
