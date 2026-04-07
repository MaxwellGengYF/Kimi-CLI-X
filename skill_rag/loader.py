"""Document loader for markdown files with frontmatter parsing."""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class Document:
    """Represents a document chunk with metadata."""
    content: str
    metadata: Dict[str, Any]
    source: str
    chunk_index: int = 0


class MarkdownLoader:
    """Load and chunk markdown files with YAML frontmatter support."""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """Initialize loader with chunking parameters.
        
        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def load_file(self, file_path: Path) -> List[Document]:
        """Load a single markdown file and return document chunks.
        
        Args:
            file_path: Path to markdown file
            
        Returns:
            List of Document chunks
        """
        content = file_path.read_text(encoding='utf-8')
        frontmatter, body = self._parse_frontmatter(content)
        
        # Chunk by headers to preserve semantic structure
        chunks = self._chunk_by_headers(body)
        
        documents = []
        for i, chunk in enumerate(chunks):
            doc = Document(
                content=chunk,
                metadata={
                    'source': str(file_path),
                    'filename': file_path.name,
                    'name': frontmatter.get('name', file_path.stem),
                    **{k: v for k, v in frontmatter.items() if k != 'name'}
                },
                source=str(file_path),
                chunk_index=i
            )
            documents.append(doc)
        
        return documents
    
    def load_directory(self, directory: Path, pattern: str = "*.md") -> List[Document]:
        """Load all markdown files from a directory.
        
        Args:
            directory: Directory to search
            pattern: Glob pattern for files
            
        Returns:
            List of all Document chunks
        """
        documents = []
        for file_path in sorted(directory.rglob(pattern)):
            docs = self.load_file(file_path)
            documents.extend(docs)
        return documents
    
    def _parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """Parse YAML frontmatter from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Tuple of (frontmatter dict, body content)
        """
        # Match YAML frontmatter between --- markers
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
                body = match.group(2)
                return frontmatter, body
            except yaml.YAMLError:
                pass
        
        # No valid frontmatter found
        return {}, content
    
    def _chunk_by_headers(self, content: str) -> List[str]:
        """Split content by headers (##) to preserve semantic structure.
        
        Args:
            content: Markdown body content
            
        Returns:
            List of content chunks
        """
        # Split by ## headers
        sections = re.split(r'\n(?=##\s)', content)
        
        chunks = []
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            # If section is too long, split further by paragraphs
            if len(section) > self.chunk_size:
                chunks.extend(self._split_large_section(section))
            else:
                chunks.append(section)
        
        return chunks if chunks else [content.strip()]
    
    def _split_large_section(self, section: str) -> List[str]:
        """Split a large section into smaller chunks.
        
        Args:
            section: Large text section
            
        Returns:
            List of smaller chunks
        """
        chunks = []
        paragraphs = [p.strip() for p in section.split('\n\n') if p.strip()]
        
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            
            if current_size + para_size > self.chunk_size and current_chunk:
                # Save current chunk
                chunks.append('\n\n'.join(current_chunk))
                # Start new chunk with overlap
                overlap_text = '\n\n'.join(current_chunk[-2:]) if len(current_chunk) >= 2 else current_chunk[-1]
                current_chunk = [overlap_text, para] if len(current_chunk) >= 2 else [para]
                current_size = len(overlap_text) + para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        
        # Add remaining content
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks
