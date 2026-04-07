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
    start_line: int = 0    # Starting line number in source file
    end_line: int = 0      # Ending line number in source file


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
        frontmatter, body, frontmatter_line_count = self._parse_frontmatter(content)
        
        # Chunk by headers to preserve semantic structure
        chunks = self._chunk_by_headers(body, frontmatter_line_count)
        
        documents = []
        for i, (chunk, start_line, end_line) in enumerate(chunks):
            doc = Document(
                content=chunk,
                metadata={
                    'source': str(file_path),
                    'filename': file_path.name,
                    'name': frontmatter.get('name', file_path.stem),
                    **{k: v for k, v in frontmatter.items() if k != 'name'}
                },
                source=str(file_path),
                chunk_index=i,
                start_line=start_line,
                end_line=end_line
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
    
    def _parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str, int]:
        """Parse YAML frontmatter from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Tuple of (frontmatter dict, body content, frontmatter line count)
        """
        # Match YAML frontmatter between --- markers
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
                body = match.group(2)
                # Count lines before body starts (more accurate than counting in group(1))
                text_before_body = content[:match.start(2)]
                frontmatter_lines = text_before_body.count('\n')
                return frontmatter, body, frontmatter_lines
            except yaml.YAMLError:
                pass
        
        # No valid frontmatter found
        return {}, content, 0
    
    def _chunk_by_headers(self, content: str, frontmatter_offset: int = 0) -> List[tuple[str, int, int]]:
        """Split content by headers (##) to preserve semantic structure.
        
        Args:
            content: Markdown body content
            frontmatter_offset: Number of lines to add to line numbers (from frontmatter)
            
        Returns:
            List of tuples: (chunk_content, start_line, end_line)
        """
        lines = content.splitlines()
        
        # Split by ## headers while tracking line numbers
        section_boundaries = [0]  # Start of first section
        for i, line in enumerate(lines):
            if re.match(r'^##\s', line):
                section_boundaries.append(i)
        
        # Add end boundary
        section_boundaries.append(len(lines))
        
        chunks = []
        for i in range(len(section_boundaries) - 1):
            start_idx = section_boundaries[i]
            end_idx = section_boundaries[i + 1]
            
            # Extract section lines
            section_lines = lines[start_idx:end_idx]
            section = '\n'.join(section_lines).strip()
            
            if not section:
                continue
            
            # Calculate line numbers (1-indexed, including frontmatter offset)
            start_line = start_idx + frontmatter_offset + 1  # +1 for 1-indexed
            end_line = end_idx + frontmatter_offset  # Don't add +1 here, end_idx is exclusive
            
            # If section is too long, split further by paragraphs
            if len(section) > self.chunk_size:
                chunks.extend(self._split_large_section(section, start_line))
            else:
                chunks.append((section, start_line, end_line))
        
        return chunks if chunks else [(content.strip(), frontmatter_offset + 1, frontmatter_offset + len(lines))]
    
    def _split_large_section(self, section: str, section_start_line: int) -> List[tuple[str, int, int]]:
        """Split a large section into smaller chunks while preserving line number info.
        
        Args:
            section: Large text section
            section_start_line: Starting line number of this section in the source file
            
        Returns:
            List of tuples: (chunk_content, start_line, end_line)
        """
        lines = section.splitlines()
        paragraphs = []
        para_start_lines = []
        
        current_para = []
        current_para_start = 0
        
        for i, line in enumerate(lines):
            if line.strip() == '' and current_para:
                # End of paragraph
                paragraphs.append('\n'.join(current_para).strip())
                para_start_lines.append(section_start_line + current_para_start)
                current_para = []
                current_para_start = i + 1
            else:
                current_para.append(line)
        
        # Add last paragraph
        if current_para:
            paragraphs.append('\n'.join(current_para).strip())
            para_start_lines.append(section_start_line + current_para_start)
        
        if not paragraphs:
            return [(section.strip(), section_start_line, section_start_line + len(lines) - 1)]
        
        chunks = []
        current_chunk_paras = []  # List of (para_index, para_text)
        current_chunk_start_line = para_start_lines[0]
        current_size = 0
        
        def calc_end_line(para_idx: int, para_text: str) -> int:
            """Calculate end line for a paragraph."""
            para_start = para_start_lines[para_idx]
            para_lines = para_text.count('\n') + 1
            return para_start + para_lines - 1
        
        def save_chunk():
            """Save current chunk to results."""
            if current_chunk_paras:
                chunk_text = '\n\n'.join(p[1] for p in current_chunk_paras)
                first_para_idx = current_chunk_paras[0][0]
                last_para_idx = current_chunk_paras[-1][0]
                start = para_start_lines[first_para_idx]
                end = calc_end_line(last_para_idx, current_chunk_paras[-1][1])
                chunks.append((chunk_text, start, end))
        
        for i, para in enumerate(paragraphs):
            if not para:
                continue
                
            para_size = len(para)
            
            if current_size + para_size > self.chunk_size and current_chunk_paras:
                # Save current chunk
                save_chunk()
                
                # Start new chunk with overlap (last 1-2 paragraphs)
                overlap_count = min(2, len(current_chunk_paras))
                overlap_paras = current_chunk_paras[-overlap_count:]
                current_chunk_paras = overlap_paras + [(i, para)]
                current_chunk_start_line = para_start_lines[overlap_paras[0][0]]
                current_size = sum(len(p[1]) for p in current_chunk_paras)
            else:
                current_chunk_paras.append((i, para))
                current_size += para_size
        
        # Add remaining content
        save_chunk()
        
        return chunks
