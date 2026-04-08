"""Document loaders for RAG pipeline.

This module provides backward-compatible aliases to the unified loader system
in document_loaders.py. New code should use document_loaders.py directly.

The following loaders are available:
- Document: Document dataclass for storing content and metadata
- MarkdownLoader: Load and chunk markdown files with frontmatter support
- PDFLoader: Load and chunk PDF files
- DocxLoader: Load and chunk Word documents (backward compatibility alias for WordLoader)
- UniversalDocumentLoader: Auto-detect and load any supported format (backward compatibility alias)
- TextLoader: Load any text file with encoding detection
- sanitize_metadata: Utility to make metadata ChromaDB-compatible
"""

from pathlib import Path

# =============================================================================
# Import from the unified document_loaders module
# =============================================================================

from .document_loaders import (
    # Core data structures
    Document,
    sanitize_metadata,
    
    # Base loader (exported for backward compatibility)
    BaseLoader,
    
    # Specific format loaders
    TextLoader,
    MarkdownLoader,
    PDFLoader,
    WordLoader,
    AutoLoader,
    
    # Utility functions
    get_loader_for_file,
)

# =============================================================================
# Backward Compatibility Aliases
# =============================================================================

# DocxLoader is the old name for WordLoader
DocxLoader = WordLoader


class UniversalDocumentLoader(AutoLoader):
    """Universal document loader with backward compatibility.
    
    This class extends AutoLoader to provide backward compatibility with
    the legacy UniversalDocumentLoader API from skill_rag.loader.
    
    New code should use AutoLoader directly from document_loaders.
    
    Additional features over AutoLoader:
    - load_text() method for loading inline text content
    - is_supported() classmethod for checking file format support
    """
    
    def load_text(
        self,
        text: str,
        source: str = "inline",
        metadata: dict | None = None,
    ) -> list[Document]:
        """Load and chunk text content directly.
        
        This method chunks the provided text using line-based chunking.
        It's useful for indexing inline text without reading from a file.
        
        Args:
            text: The text content to load and chunk
            source: Source identifier for the content (default: "inline")
            metadata: Optional metadata to attach to documents
            
        Returns:
            List of Document objects with chunked content
        """
        if not text or not text.strip():
            return []
        
        base_metadata = metadata or {}
        
        # Use line-based chunking (similar to TextLoader)
        lines = text.splitlines()
        chunks = []
        current_chunk_lines = []
        current_size = 0
        chunk_start_line = 1
        
        for i, line in enumerate(lines, start=1):
            line_size = len(line) + 1  # +1 for newline
            
            if current_size + line_size > self.chunk_size and current_chunk_lines:
                # Save current chunk
                chunk_text = '\n'.join(current_chunk_lines)
                chunk_metadata = {
                    **base_metadata,
                    'total_lines': len(lines),
                }
                doc = Document(
                    content=chunk_text,
                    metadata=sanitize_metadata(chunk_metadata),
                    source=source,
                    chunk_index=len(chunks),
                    start_line=chunk_start_line,
                    end_line=i - 1,
                )
                chunks.append(doc)
                
                # Start new chunk with overlap
                overlap_lines = current_chunk_lines[-self.chunk_overlap:] if self.chunk_overlap > 0 else []
                current_chunk_lines = overlap_lines + [line]
                current_size = sum(len(l) + 1 for l in current_chunk_lines)
                chunk_start_line = i - len(overlap_lines)
            else:
                current_chunk_lines.append(line)
                current_size += line_size
        
        # Don't forget the last chunk
        if current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines)
            chunk_metadata = {
                **base_metadata,
                'total_lines': len(lines),
            }
            doc = Document(
                content=chunk_text,
                metadata=sanitize_metadata(chunk_metadata),
                source=source,
                chunk_index=len(chunks),
                start_line=chunk_start_line,
                end_line=len(lines),
            )
            chunks.append(doc)
        
        return chunks
    
    @classmethod
    def is_supported(cls, file_path: str | Path) -> bool:
        """Check if a file format is supported.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if the file format is supported, False otherwise
        """
        try:
            path = Path(file_path)
            extension = path.suffix.lower()
            
            # Check if we have a loader for this extension
            # TextLoader supports many extensions, so we need to check all
            # supported patterns
            
            # First check known document formats
            known_formats = {'.md', '.markdown', '.pdf', '.docx', '.doc'}
            if extension in known_formats:
                return True
            
            # Check if TextLoader supports it (includes code and text files)
            text_loader = TextLoader()
            if text_loader._is_text_file(path):
                return True
            
            # Try get_loader_for_file to see if it returns a loader
            try:
                loader = get_loader_for_file(path)
                return loader is not None
            except ValueError:
                return False
                
        except Exception:
            return False


# =============================================================================
# Re-export for backward compatibility
# =============================================================================

__all__ = [
    # Core classes and functions
    'Document',
    'sanitize_metadata',
    'BaseLoader',
    
    # Specific loaders
    'TextLoader',      # Supports any text format
    'MarkdownLoader',  # Markdown with frontmatter
    'PDFLoader',       # PDF documents
    'WordLoader',      # Word documents (modern name)
    'DocxLoader',      # Word documents (backward compatibility)
    'AutoLoader',      # Universal loader (modern name)
    
    # Universal loader (backward compatibility)
    'UniversalDocumentLoader',
    
    # Utility functions
    'get_loader_for_file',
]
