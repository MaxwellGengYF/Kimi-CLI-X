"""RAG Pipeline that orchestrates document loading, embedding, and retrieval."""

import hashlib
import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Union
from dataclasses import dataclass

from skill_rag.loader import MarkdownLoader, Document, UniversalDocumentLoader
from skill_rag.embeddings import EmbeddingService, SentenceTransformerEmbedder
from skill_rag.embedding_cache import CachedEmbedder, EmbeddingCache
from skill_rag.config import get_config
from skill_rag.vector_store import ChromaVectorStore
from skill_rag.reranker import Reranker, CrossEncoderReranker
from skill_rag.hybrid_search import HybridSearcher, HybridSearchResult
from skill_rag.query_optimizer import QueryOptimizer, create_optimizer
from skill_rag.file_tracker import FileTracker, compute_file_hash

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result from a RAG query."""
    content: str
    metadata: Dict[str, Any]
    distance: float
    source: str
    start_line: int = 0
    end_line: int = 0


@dataclass
class IndexingResult:
    """Result from indexing operation."""
    new_chunks: int
    skipped_chunks: int
    updated_chunks: int
    total_chunks: int
    errors: List[str]


class RAGPipeline:
    """Main RAG pipeline for indexing and querying documents."""
    
    def __init__(
        self,
        collection_name: str = "skill_docs",
        persist_directory: str = "./chroma_db",
        embedding_model: Optional[str] = "all-MiniLM-L6-v2",
        use_reranker: bool = False,
        reranker_model: Optional[str] = None,
        use_hybrid_search: bool = False,
        alpha: float = 0.5,
        use_query_optimizer: bool = False,
        query_optimizer_mode: str = "expansion",
        enable_file_tracking: bool = True,
        use_embedding_cache: bool = True,
        cache_dir: Optional[str] = None,
        use_semantic_chunking: bool = False
    ):
        """Initialize the RAG pipeline.
        
        Args:
            collection_name: Name for the ChromaDB collection
            persist_directory: Directory for persistent storage
            embedding_model: Name of embedding model to use (None for legacy EmbeddingService)
            use_reranker: Whether to use reranking
            reranker_model: Reranker model name (None for default)
            use_hybrid_search: Whether to use hybrid search (BM25 + vector)
            alpha: Weight for vector search in hybrid (0=BM25, 1=vector, 0.5=balanced)
            use_query_optimizer: Whether to optimize queries before search
            query_optimizer_mode: Query optimizer mode ("none", "expansion", "hyde", "full")
            enable_file_tracking: Whether to enable incremental file indexing
            use_embedding_cache: Whether to enable embedding caching
            cache_dir: Directory for embedding cache (None for default)
            use_semantic_chunking: Use semantic chunking with paragraph/sentence boundaries
        """
        # Persist directory for tracking files
        self.persist_directory = Path(persist_directory) if persist_directory else None
        
        # Document loader supports multiple formats with optional semantic chunking
        self.loader = UniversalDocumentLoader(
            chunk_size=1500,
            chunk_overlap=100,
            use_semantic_chunking=use_semantic_chunking
        )
        
        # Embedding model selection with optional caching
        if embedding_model:
            try:
                base_embedder = SentenceTransformerEmbedder(model_name=embedding_model)
            except Exception as e:
                logger.warning(f"Failed to load {embedding_model}: {e}. Using fallback embedder.")
                base_embedder = EmbeddingService(dimension=384)
        else:
            # Legacy embedder
            base_embedder = EmbeddingService(dimension=384)
        
        # Wrap with cache if enabled
        if use_embedding_cache:
            if cache_dir:
                cache_path = Path(cache_dir)
            elif self.persist_directory:
                cache_path = self.persist_directory / "embedding_cache"
            else:
                cache_path = Path(".embedding_cache")
            self.embedder = CachedEmbedder(
                base_embedder,
                cache_dir=cache_path,
                enabled=True
            )
            logger.info(f"Embedding cache enabled at {cache_path}")
        else:
            self.embedder = base_embedder
        
        # Vector store
        self.store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_dimension=self.embedder.dimension
        )
        
        # Optional reranker
        self.reranker: Optional[Reranker] = None
        if use_reranker:
            try:
                self.reranker = CrossEncoderReranker(model_name=reranker_model)
            except Exception as e:
                logger.warning(f"Failed to load reranker: {e}")
        
        # Optional hybrid search
        self.hybrid_searcher: Optional[HybridSearcher] = None
        self.use_hybrid_search = use_hybrid_search
        self.hybrid_alpha = alpha
        if use_hybrid_search:
            # Initialize hybrid searcher with empty corpus
            # It will be populated as documents are indexed
            self.hybrid_searcher = HybridSearcher(alpha=alpha)
            self._sync_hybrid_corpus()
        
        # Query optimizer
        self.query_optimizer: Optional[QueryOptimizer] = None
        if use_query_optimizer:
            self.query_optimizer = create_optimizer(mode=query_optimizer_mode)
        
        # File tracker for incremental indexing
        self.file_tracker: Optional[FileTracker] = None
        if enable_file_tracking:
            if self.persist_directory:
                tracker_path = self.persist_directory / f"{collection_name}_file_tracker.json"
            else:
                tracker_path = Path(f"{collection_name}_file_tracker.json")
            self.file_tracker = FileTracker(index_path=tracker_path)
        
        # Thread-safe lock for concurrent operations
        self._lock = threading.RLock()
    
    def _sync_hybrid_corpus(self) -> None:
        """Sync hybrid searcher corpus with ChromaDB contents."""
        if not self.hybrid_searcher:
            return
        
        with self._lock:
            try:
                # Get all documents from store
                results = self.store.get_by_metadata({}, limit=10000)
                
                # Build corpus
                corpus = []
                for doc in results:
                    corpus.append({
                        "id": doc.get("id", ""),
                        "text": doc.get("document", ""),
                        "metadata": doc.get("metadata", {})
                    })
                
                if corpus:
                    self.hybrid_searcher.build_corpus(corpus)
            except Exception as e:
                logger.warning(f"Failed to sync hybrid corpus: {e}")
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute hash for content deduplication."""
        return hashlib.md5(content.encode()).hexdigest()
    
    def _check_existing_document(
        self,
        content_hash: str,
        source: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if document already exists.
        
        Returns:
            Tuple of (exists, existing_id)
        """
        try:
            # Use $and operator for ChromaDB compatibility
            results = self.store.get_by_metadata(
                {"$and": [
                    {"content_hash": {"$eq": content_hash}},
                    {"source": {"$eq": source}}
                ]},
                limit=1
            )
            if results:
                return True, results[0].get("id")
        except Exception as e:
            logger.debug(f"Error checking existing document: {e}")
        return False, None
    
    def index_file(
        self,
        file_path: Path,
        skip_duplicates: bool = True,
        update_existing: bool = False,
        use_file_tracking: bool = True
    ) -> IndexingResult:
        """Index a single file (supports .md, .pdf, .docx).
        
        Uses file tracking for incremental indexing when enabled.
        This method is thread-safe.
        
        Args:
            file_path: Path to file
            skip_duplicates: Skip if already indexed (ignored if file_tracking enabled)
            update_existing: Update if content changed (ignored if file_tracking enabled)
            use_file_tracking: Use incremental file tracking
            
        Returns:
            IndexingResult with counts
        """
        with self._lock:
            return self._index_file_unsafe(file_path, skip_duplicates, update_existing, use_file_tracking)
    
    def _index_file_unsafe(
        self,
        file_path: Path,
        skip_duplicates: bool = True,
        update_existing: bool = False,
        use_file_tracking: bool = True
    ) -> IndexingResult:
        """Index a single file (supports .md, .pdf, .docx).
        
        Uses file tracking for incremental indexing when enabled.
        
        Args:
            file_path: Path to file
            skip_duplicates: Skip if already indexed (ignored if file_tracking enabled)
            update_existing: Update if content changed (ignored if file_tracking enabled)
            use_file_tracking: Use incremental file tracking
            
        Returns:
            IndexingResult with counts
        """
        file_path = Path(file_path)
        
        # Check if file exists
        if not file_path.exists():
            return IndexingResult(0, 0, 0, 0, [f"File not found: {file_path}"])
        
        # Compute file hash for tracking
        file_hash = compute_file_hash(file_path)
        if not file_hash:
            return IndexingResult(0, 0, 0, 0, [f"Failed to read file: {file_path}"])
        
        # Check file tracker for changes
        if use_file_tracking and self.file_tracker:
            if not self.file_tracker.needs_update(file_path, file_hash):
                logger.debug(f"Skipping unchanged file: {file_path}")
                return IndexingResult(0, 1, 0, 0, [])
        
        # Load and index documents
        documents = self.loader.load_file(file_path)
        if not documents:
            return IndexingResult(0, 0, 0, 0, ["No documents loaded"])
        
        # If using file tracking, delete old chunks first
        if use_file_tracking and self.file_tracker:
            old_ids = self.file_tracker.get_doc_ids_for_file(file_path)
            if old_ids:
                try:
                    self.store.delete_by_ids(old_ids)
                    logger.debug(f"Deleted {len(old_ids)} old chunks for {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete old chunks: {e}")
        
        # Index documents without duplicate checking (we already checked via file hash)
        result = self._index_documents(
            documents,
            skip_duplicates=False,  # Already checked via file hash
            update_existing=False   # Will replace via file tracking
        )
        
        # Update file tracker with new document IDs
        if use_file_tracking and self.file_tracker and result.new_chunks > 0:
            # Get IDs of newly added documents
            new_doc_ids = []
            for doc in documents[:result.new_chunks]:
                content_hash = self._compute_content_hash(doc.content)
                doc_id = f"{doc.metadata.get('name', 'doc')}_{doc.chunk_index}_{content_hash[:8]}"
                new_doc_ids.append(doc_id)
            
            self.file_tracker.update_file(file_path, file_hash, new_doc_ids)
            self.file_tracker.save()
        
        return result
    
    def index_directory(
        self,
        directory: Path,
        pattern: str = "*",
        skip_duplicates: bool = True,
        update_existing: bool = False,
        use_file_tracking: bool = True,
        cleanup_deleted: bool = True
    ) -> IndexingResult:
        """Index all supported files in a directory.
        
        Uses file tracking for incremental indexing when enabled.
        
        Args:
            directory: Directory to search
            pattern: File pattern to match (e.g., "*.md")
            skip_duplicates: Skip if already indexed (ignored if file_tracking enabled)
            update_existing: Update if content changed (ignored if file_tracking enabled)
            use_file_tracking: Use incremental file tracking
            cleanup_deleted: Remove chunks for deleted files
            
        Returns:
            IndexingResult with counts
        """
        directory = Path(directory)
        
        if use_file_tracking and self.file_tracker:
            # Get list of files to index
            from skill_rag.loader import MarkdownLoader, PDFLoader, DocxLoader
            
            supported_patterns = ['*.md', '*.pdf', '*.docx']
            files_to_index = []
            for p in supported_patterns:
                files_to_index.extend(directory.rglob(p))
            
            # Filter by pattern if specified
            if pattern != "*":
                files_to_index = [f for f in files_to_index if f.match(pattern)]
            
            # Clean up deleted files
            deleted_chunks = 0
            if cleanup_deleted:
                current_files = set(files_to_index)
                stale_ids = self.file_tracker.cleanup_stale(current_files)
                if stale_ids:
                    try:
                        self.store.delete_by_ids(stale_ids)
                        deleted_chunks = len(stale_ids)
                        logger.info(f"Deleted {deleted_chunks} chunks from removed files")
                    except Exception as e:
                        logger.warning(f"Failed to delete stale chunks: {e}")
                self.file_tracker.save()
            
            # Index each file individually
            total_new = 0
            total_skipped = 0
            total_updated = deleted_chunks  # Count deletions as updates
            errors = []
            
            for file_path in files_to_index:
                result = self.index_file(
                    file_path,
                    use_file_tracking=True
                )
                total_new += result.new_chunks
                total_skipped += result.skipped_chunks
                total_updated += result.updated_chunks
                errors.extend(result.errors)
            
            return IndexingResult(
                new_chunks=total_new,
                skipped_chunks=total_skipped,
                updated_chunks=total_updated,
                total_chunks=total_new + total_skipped + total_updated,
                errors=errors
            )
        else:
            # Legacy mode: load all documents and index together
            documents = self.loader.load_directory(directory, pattern)
            if not documents:
                return IndexingResult(0, 0, 0, 0, ["No documents loaded"])
            
            return self._index_documents(
                documents,
                skip_duplicates=skip_duplicates,
                update_existing=update_existing
            )
    
    def index_text(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "inline",
        skip_duplicates: bool = True
    ) -> IndexingResult:
        """Index raw text content.
        
        Args:
            content: Text content to index
            metadata: Optional metadata
            source: Source identifier
            skip_duplicates: Skip if already indexed
            
        Returns:
            IndexingResult with counts
        """
        documents = self.loader.load_text(content, source, metadata)
        if not documents:
            return IndexingResult(0, 0, 0, 0, ["No documents generated"])
        
        return self._index_documents(
            documents,
            skip_duplicates=skip_duplicates
        )
    
    def index_documents(
        self,
        documents: List[Dict[str, Any]],
        skip_duplicates: bool = True,
        update_existing: bool = False
    ) -> IndexingResult:
        """Index a list of document dictionaries.
        
        Args:
            documents: List of dicts with 'content' and optional 'metadata' keys
            skip_duplicates: Skip if already indexed
            update_existing: Update if content changed
            
        Returns:
            IndexingResult with counts
        """
        # Convert dicts to Document objects
        doc_objects = []
        for i, doc in enumerate(documents):
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            source = metadata.get("source", f"inline_{i}")
            doc_objects.append(Document(content=content, metadata=metadata, source=source))
        
        return self._index_documents(
            doc_objects,
            skip_duplicates=skip_duplicates,
            update_existing=update_existing
        )
    
    def _index_documents(
        self,
        documents: List[Document],
        skip_duplicates: bool = True,
        update_existing: bool = False
    ) -> IndexingResult:
        """Index a list of documents with deduplication.
        
        Args:
            documents: List of Document objects
            skip_duplicates: Skip if already indexed
            update_existing: Update if content changed
            
        Returns:
            IndexingResult with counts
        """
        new_docs = []
        updated_docs = []
        skipped = 0
        errors = []
        
        for doc in documents:
            # Compute content hash for deduplication
            content_hash = self._compute_content_hash(doc.content)
            
            # Check for existing
            if skip_duplicates or update_existing:
                exists, existing_id = self._check_existing_document(
                    content_hash,
                    doc.metadata.get("source", "")
                )
                
                if exists:
                    if skip_duplicates and not update_existing:
                        skipped += 1
                        continue
                    elif update_existing:
                        updated_docs.append((existing_id, doc, content_hash))
                        continue
            
            new_docs.append((doc, content_hash))
        
        # Process new documents
        indexed = 0
        if new_docs:
            try:
                indexed = self._add_doc_batch(new_docs)
            except Exception as e:
                errors.append(f"Error indexing new documents: {e}")
        
        # Process updates
        updated = 0
        if updated_docs:
            for existing_id, doc, content_hash in updated_docs:
                try:
                    self._update_doc(existing_id, doc, content_hash)
                    updated += 1
                except Exception as e:
                    errors.append(f"Error updating document {existing_id}: {e}")
        
        # Sync hybrid searcher if needed
        if (new_docs or updated_docs) and self.hybrid_searcher:
            self._sync_hybrid_corpus()
        
        return IndexingResult(
            new_chunks=indexed,
            skipped_chunks=skipped,
            updated_chunks=updated,
            total_chunks=len(documents),
            errors=errors
        )
    
    def _add_doc_batch(self, docs_with_hash: List[Tuple[Document, str]]) -> int:
        """Add a batch of new documents."""
        documents = []
        embeddings = []
        metadatas = []
        ids = []
        
        for doc, content_hash in docs_with_hash:
            # Generate embedding
            emb = self.embedder.embed([doc.content])[0]
            
            # Prepare metadata
            metadata = {
                **doc.metadata,
                "chunk_index": doc.chunk_index,
                "start_line": doc.start_line,
                "end_line": doc.end_line,
                "content_hash": content_hash,
            }
            
            # Generate unique ID
            doc_id = f"{doc.metadata.get('name', 'doc')}_{doc.chunk_index}_{content_hash[:8]}"
            
            documents.append(doc.content)
            embeddings.append(emb)
            metadatas.append(metadata)
            ids.append(doc_id)
        
        # Add to store (store.add_documents is already thread-safe)
        self.store.add_documents(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        
        return len(docs_with_hash)
    
    def _update_doc(self, existing_id: str, doc: Document, content_hash: str) -> None:
        """Update an existing document."""
        # Generate new embedding
        emb = self.embedder.embed([doc.content])[0]
        
        # Prepare metadata
        metadata = {
            **doc.metadata,
            "chunk_index": doc.chunk_index,
            "start_line": doc.start_line,
            "end_line": doc.end_line,
            "content_hash": content_hash,
        }
        
        # Update in store (store.update_document is already thread-safe)
        self.store.update_document(
            id=existing_id,
            document=doc.content,
            embedding=emb,
            metadata=metadata
        )
    
    def query(
        self,
        query_text: str,
        top_k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None,
        use_rerank: Optional[bool] = None,
        use_hybrid: Optional[bool] = None
    ) -> List[QueryResult]:
        """Query the indexed documents.
        
        Args:
            query_text: Query text
            top_k: Number of results to return
            filter_dict: Optional metadata filter
            use_rerank: Override reranking (None uses pipeline default)
            use_hybrid: Override hybrid search (None uses pipeline default)
            
        Returns:
            List of QueryResult objects
        """
        # Determine which methods to use
        do_rerank = use_rerank if use_rerank is not None else (self.reranker is not None)
        do_hybrid = use_hybrid if use_hybrid is not None else self.use_hybrid_search
        
        # Optimize query if optimizer is enabled
        optimized_query = query_text
        if self.query_optimizer:
            optimized_query = self.query_optimizer.optimize_for_vector_search(query_text)
        
        # Retrieve candidates
        if do_hybrid and self.hybrid_searcher:
            # Hybrid search
            keyword_query = query_text
            if self.query_optimizer:
                keyword_query = self.query_optimizer.optimize_for_keyword_search(query_text)
            
            results = self._hybrid_query(
                optimized_query,
                keyword_query,
                top_k=top_k * 3 if do_rerank else top_k,
                filter_dict=filter_dict
            )
        else:
            # Vector-only search
            results = self._vector_query(
                optimized_query,
                top_k=top_k * 3 if do_rerank else top_k,
                filter_dict=filter_dict
            )
        
        # Rerank if enabled
        if do_rerank and self.reranker and results:
            results = self._rerank_results(query_text, results, top_k)
        elif len(results) > top_k:
            results = results[:top_k]
        
        return results
    
    def _vector_query(
        self,
        query_text: str,
        top_k: int,
        filter_dict: Optional[Dict[str, Any]]
    ) -> List[QueryResult]:
        """Perform vector similarity search."""
        query_embedding = self.embedder.embed_query(query_text)
        
        results = self.store.query(
            query_embedding=query_embedding,
            n_results=top_k,
            filter_dict=filter_dict
        )
        
        return self._parse_results(results)
    
    def _hybrid_query(
        self,
        vector_query: str,
        keyword_query: str,
        top_k: int,
        filter_dict: Optional[Dict[str, Any]]
    ) -> List[QueryResult]:
        """Perform hybrid search (BM25 + vector)."""
        if not self.hybrid_searcher:
            return []
        
        # Ensure corpus is up to date
        if not self.hybrid_searcher._corpus:
            self._sync_hybrid_corpus()
        
        # Get vector embedding
        query_embedding = self.embedder.embed_query(vector_query)
        
        # Perform hybrid search
        results = self.hybrid_searcher.search(
            query=keyword_query,
            query_embedding=query_embedding,
            top_k=top_k,
            filter_dict=filter_dict
        )
        
        # Convert to QueryResult
        query_results = []
        for result in results:
            query_results.append(QueryResult(
                content=result.content,
                metadata=result.metadata,
                distance=1.0 - result.score,  # Convert score to distance
                source=result.metadata.get("source", ""),
                start_line=result.metadata.get("start_line", 0),
                end_line=result.metadata.get("end_line", 0),
            ))
        
        return query_results
    
    def _rerank_results(
        self,
        query: str,
        results: List[QueryResult],
        top_k: int
    ) -> List[QueryResult]:
        """Rerank results using cross-encoder."""
        if not self.reranker or not results:
            return results
        
        documents = [r.content for r in results]
        ranked = self.reranker.rerank(query, documents, top_k=top_k)
        
        # Map back to QueryResults
        doc_to_result = {r.content: r for r in results}
        reranked_results = []
        
        for doc_text, score in ranked:
            if doc_text in doc_to_result:
                result = doc_to_result[doc_text]
                # Update score (reranker score is typically 0-1)
                result.distance = 1.0 - score
                reranked_results.append(result)
        
        return reranked_results
    
    def _parse_results(self, results: Dict[str, Any]) -> List[QueryResult]:
        """Parse ChromaDB results into QueryResult objects."""
        query_results = []
        
        if not results.get("documents") or not results["documents"][0]:
            return query_results
        
        for i in range(len(results["documents"][0])):
            metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
            query_results.append(QueryResult(
                content=results["documents"][0][i],
                metadata=metadata,
                distance=results["distances"][0][i] if results.get("distances") else 0.0,
                source=metadata.get("source", ""),
                start_line=metadata.get("start_line", 0),
                end_line=metadata.get("end_line", 0),
            ))
        
        return query_results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        stats = self.store.get_stats()
        stats.update({
            "embedding_model": getattr(self.embedder, 'model_name', 'legacy'),
            "embedding_dimension": self.embedder.dimension,
            "reranker_enabled": self.reranker is not None,
            "reranker_model": getattr(self.reranker, 'model_name', None) if self.reranker else None,
            "hybrid_search_enabled": self.use_hybrid_search,
            "hybrid_alpha": self.hybrid_alpha if self.use_hybrid_search else None,
            "query_optimizer_enabled": self.query_optimizer is not None,
            "file_tracking_enabled": self.file_tracker is not None,
        })
        
        # Add file tracking stats if enabled
        if self.file_tracker:
            stats["file_tracking"] = self.file_tracker.get_stats()
        
        return stats
    
    def get_file_tracking_info(self) -> Optional[Dict[str, Any]]:
        """Get file tracking information.
        
        Returns:
            File tracking stats or None if not enabled
        """
        if not self.file_tracker:
            return None
        return self.file_tracker.get_stats()
    
    def force_reindex_file(self, file_path: Path) -> IndexingResult:
        """Force re-index a file even if unchanged.
        
        Args:
            file_path: Path to file
            
        Returns:
            IndexingResult with counts
        """
        # Clear the file tracker entry for this file
        if self.file_tracker:
            self.file_tracker.remove_file(file_path)
            self.file_tracker.save()
        
        # Re-index the file
        return self.index_file(file_path, use_file_tracking=True)
    
    def reset(self) -> None:
        """Reset the pipeline (clear all indexed data)."""
        self.store.reset()
        if self.hybrid_searcher:
            self.hybrid_searcher.clear()
        if self.file_tracker:
            self.file_tracker.clear()
    
    def delete_collection(self) -> None:
        """Delete the entire collection."""
        self.store.delete_collection()
        if self.hybrid_searcher:
            self.hybrid_searcher.clear()
        if self.file_tracker:
            self.file_tracker.clear()
    
    def delete_by_source(self, source: str) -> int:
        """Delete all documents from a specific source.
        
        This method is thread-safe.
        
        Args:
            source: Source file path or identifier
            
        Returns:
            Number of documents deleted
        """
        with self._lock:
            count = self.store.delete_by_filter({"source": source})
            if count > 0 and self.hybrid_searcher:
                self._sync_hybrid_corpus()
            return count
    
    def update_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update a specific document.
        
        This method is thread-safe.
        
        Args:
            doc_id: Document ID
            content: New content
            metadata: Optional metadata
            
        Returns:
            True if successful
        """
        with self._lock:
            try:
                embedding = self.embedder.embed([content])[0]
                
                # Compute new hash
                content_hash = self._compute_content_hash(content)
                meta = metadata or {}
                meta["content_hash"] = content_hash
                
                self.store.update_document(doc_id, content, embedding, meta)
                
                if self.hybrid_searcher:
                    self._sync_hybrid_corpus()
                
                return True
            except Exception as e:
                logger.error(f"Failed to update document {doc_id}: {e}")
                return False
