"""RAG Pipeline that orchestrates document loading, embedding, and retrieval."""

from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from skill_rag.loader import MarkdownLoader, Document
from skill_rag.embeddings import EmbeddingService
from skill_rag.vector_store import ChromaVectorStore


@dataclass
class QueryResult:
    """Result from a RAG query."""
    content: str
    metadata: Dict[str, Any]
    distance: float
    source: str
    start_line: int = 0    # Starting line number in source file
    end_line: int = 0      # Ending line number in source file


class RAGPipeline:
    """Main RAG pipeline for indexing and querying documents."""
    
    def __init__(
        self,
        collection_name: str = "skill_docs",
        persist_directory: str = "./chroma_db",
        embedding_model: Optional[str] = None
    ):
        """Initialize the RAG pipeline.
        
        Args:
            collection_name: Name for the ChromaDB collection
            persist_directory: Directory for persistent storage
            embedding_model: Name of embedding model to use
        """
        self.loader = MarkdownLoader(chunk_size=1500, chunk_overlap=100)
        self.embedder = EmbeddingService(dimension=384)
        self.store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_dimension=self.embedder.dimension
        )
    
    def index_file(self, file_path: Path) -> int:
        """Index a single markdown file.
        
        Args:
            file_path: Path to markdown file
            
        Returns:
            Number of chunks indexed
        """
        documents = self.loader.load_file(file_path)
        return self._index_documents(documents)
    
    def index_directory(self, directory: Path, pattern: str = "*.md") -> int:
        """Index all markdown files in a directory.
        
        Args:
            directory: Directory to search
            pattern: File pattern to match
            
        Returns:
            Total number of chunks indexed
        """
        documents = self.loader.load_directory(directory, pattern)
        return self._index_documents(documents)
    
    def _index_documents(self, documents: List[Document]) -> int:
        """Index a list of documents.
        
        Args:
            documents: List of Document objects
            
        Returns:
            Number of documents indexed
        """
        if not documents:
            return 0
        
        # Generate embeddings
        texts = [doc.content for doc in documents]
        embeddings = self.embedder.embed(texts)
        
        # Prepare metadata
        metadatas = [
            {
                **doc.metadata,
                "chunk_index": doc.chunk_index,
                "start_line": doc.start_line,
                "end_line": doc.end_line,
            }
            for doc in documents
        ]
        
        # Generate unique IDs
        ids = [
            f"{doc.metadata.get('name', 'doc')}_{doc.chunk_index}_{i}"
            for i, doc in enumerate(documents)
        ]
        
        # Add to store
        self.store.add_documents(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        
        return len(documents)
    
    def query(
        self,
        query_text: str,
        top_k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[QueryResult]:
        """Query the indexed documents.
        
        Args:
            query_text: Query text
            top_k: Number of results to return
            filter_dict: Optional metadata filter
            
        Returns:
            List of QueryResult objects
        """
        # Generate query embedding
        query_embedding = self.embedder.embed_query(query_text)
        
        # Query store
        results = self.store.query(
            query_embedding=query_embedding,
            n_results=top_k,
            filter_dict=filter_dict
        )
        
        # Parse results
        query_results = []
        if results["documents"] and results["documents"][0]:
            for i in range(len(results["documents"][0])):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                query_results.append(QueryResult(
                    content=results["documents"][0][i],
                    metadata=metadata,
                    distance=results["distances"][0][i] if results["distances"] else 0.0,
                    source=metadata.get("source", ""),
                    start_line=metadata.get("start_line", 0),
                    end_line=metadata.get("end_line", 0),
                ))
        
        return query_results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics.
        
        Returns:
            Dict with stats
        """
        return {
            **self.store.get_stats(),
            "embedding_model": "Word2Vec/glove-wiki-gigaword-100"
        }
    
    def reset(self) -> None:
        """Reset the pipeline (clear all indexed data)."""
        self.store.reset()
    
    def delete_collection(self) -> None:
        """Delete the entire collection."""
        self.store.delete_collection()
