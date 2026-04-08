"""Semantic chunking for natural language documents.

This module provides intelligent text chunking that respects semantic boundaries
like paragraphs and sentences, producing more coherent chunks than fixed-size
character-based splitting.
"""

import re
from typing import List, Iterator, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Chunk:
    """A text chunk with metadata."""
    content: str
    start_pos: int
    end_pos: int
    index: int


class SemanticChunker:
    """Chunks text at semantic boundaries (paragraphs, sentences).
    
    Uses a hierarchical approach:
    1. First tries to split at paragraph boundaries
    2. Then at sentence boundaries within paragraphs
    3. Finally at word boundaries if necessary
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        respect_paragraphs: bool = True
    ):
        """Initialize the semantic chunker.
        
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks in characters
            respect_paragraphs: Whether to avoid splitting paragraphs
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.respect_paragraphs = respect_paragraphs
    
    def chunk_text(self, text: str) -> List[str]:
        """Split text into semantic chunks (returns text strings).
        
        Args:
            text: Input text to chunk
            
        Returns:
            List of text chunks
        """
        chunks = self.chunk(text)
        return [chunk.content for chunk in chunks]
    
    def chunk(self, text: str) -> List[Chunk]:
        """Split text into semantic chunks.
        
        Args:
            text: Input text to chunk
            
        Returns:
            List of Chunk objects
        """
        if not text.strip():
            return []
        
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Get semantic boundaries
        paragraphs = self._split_paragraphs(text)
        
        chunks = []
        chunk_index = 0
        current_pos = 0
        
        for para_idx, paragraph in enumerate(paragraphs):
            para_start = text.find(paragraph, current_pos)
            if para_start == -1:
                para_start = current_pos
            para_end = para_start + len(paragraph)
            
            # If paragraph fits within chunk size, add it
            if len(paragraph) <= self.chunk_size:
                # Check if we can append to the last chunk
                if (chunks and 
                    len(chunks[-1].content) + len(paragraph) + 1 <= self.chunk_size):
                    # Merge with previous chunk
                    old_chunk = chunks[-1]
                    merged_content = old_chunk.content + '\n\n' + paragraph
                    chunks[-1] = Chunk(
                        content=merged_content,
                        start_pos=old_chunk.start_pos,
                        end_pos=para_end,
                        index=old_chunk.index
                    )
                else:
                    chunks.append(Chunk(
                        content=paragraph,
                        start_pos=para_start,
                        end_pos=para_end,
                        index=chunk_index
                    ))
                    chunk_index += 1
            else:
                # Paragraph is too long, split at sentence boundaries
                para_chunks = self._chunk_large_paragraph(
                    paragraph, para_start, chunk_index
                )
                chunks.extend(para_chunks)
                chunk_index += len(para_chunks)
            
            current_pos = para_end
        
        # Apply overlap if specified
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks)
        
        return chunks
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs.
        
        Handles various paragraph separators:
        - Double newlines (\n\n)
        - Multiple blank lines
        - Markdown headers (treated as paragraph boundaries)
        """
        # Split on double newlines or more
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Clean up and filter empty paragraphs
        result = []
        for para in paragraphs:
            para = para.strip()
            if para:
                result.append(para)
        
        return result
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using a simple but robust approach.
        
        Handles basic sentence boundaries while avoiding complex regex issues.
        """
        if not text or not text.strip():
            return []
        
        # Simple approach: split on .!? followed by space and capital letter
        # or end of string
        sentences = []
        current = []
        words = text.split()
        
        for i, word in enumerate(words):
            current.append(word)
            # Check if word ends with sentence terminator
            if word[-1] in '.!?':
                # Check if it's the last word or next word starts with capital
                if i == len(words) - 1:
                    sentences.append(' '.join(current))
                    current = []
                elif words[i + 1][0].isupper():
                    sentences.append(' '.join(current))
                    current = []
        
        # Add any remaining text
        if current:
            sentences.append(' '.join(current))
        
        return sentences if sentences else [text.strip()]
    
    def _chunk_large_paragraph(
        self,
        paragraph: str,
        start_pos: int,
        start_index: int
    ) -> List[Chunk]:
        """Chunk a large paragraph at sentence boundaries."""
        sentences = self._split_sentences(paragraph)
        
        chunks = []
        current_chunk_sentences = []
        current_length = 0
        chunk_index = start_index
        
        for sentence in sentences:
            sent_len = len(sentence)
            
            # If sentence itself is too long, split it at word boundaries
            if sent_len > self.chunk_size:
                # First, flush any accumulated sentences
                if current_chunk_sentences:
                    chunk_text = ' '.join(current_chunk_sentences)
                    chunk_start = start_pos + paragraph.find(current_chunk_sentences[0])
                    chunk_end = chunk_start + len(chunk_text)
                    
                    chunks.append(Chunk(
                        content=chunk_text,
                        start_pos=chunk_start,
                        end_pos=chunk_end,
                        index=chunk_index
                    ))
                    chunk_index += 1
                    current_chunk_sentences = []
                    current_length = 0
                
                # Now split the long sentence at word boundaries
                words = sentence.split()
                current_chunk_words = []
                current_word_length = 0
                word_start_offset = paragraph.find(sentence)
                
                for word in words:
                    word_len = len(word)
                    # Check if adding this word exceeds chunk size
                    if current_word_length + word_len + (1 if current_chunk_words else 0) > self.chunk_size:
                        # Flush current chunk
                        if current_chunk_words:
                            chunk_text = ' '.join(current_chunk_words)
                            chunk_start = start_pos + word_start_offset
                            chunk_end = chunk_start + len(chunk_text)
                            
                            chunks.append(Chunk(
                                content=chunk_text,
                                start_pos=chunk_start,
                                end_pos=chunk_end,
                                index=chunk_index
                            ))
                            chunk_index += 1
                            
                            # Update offset for next chunk
                            word_start_offset += len(chunk_text) + 1  # +1 for the space
                        
                        current_chunk_words = [word]
                        current_word_length = word_len
                    else:
                        current_chunk_words.append(word)
                        current_word_length += word_len + (1 if len(current_chunk_words) > 1 else 0)
                
                # Add remaining words from sentence
                if current_chunk_words:
                    chunk_text = ' '.join(current_chunk_words)
                    chunk_start = start_pos + word_start_offset
                    chunk_end = chunk_start + len(chunk_text)
                    
                    chunks.append(Chunk(
                        content=chunk_text,
                        start_pos=chunk_start,
                        end_pos=chunk_end,
                        index=chunk_index
                    ))
                    chunk_index += 1
                
                continue  # Move to next sentence
            
            # If adding this sentence exceeds chunk size, finalize current chunk
            if current_length + sent_len + (1 if current_chunk_sentences else 0) > self.chunk_size:
                if current_chunk_sentences:
                    chunk_text = ' '.join(current_chunk_sentences)
                    chunk_start = start_pos + paragraph.find(current_chunk_sentences[0])
                    chunk_end = chunk_start + len(chunk_text)
                    
                    chunks.append(Chunk(
                        content=chunk_text,
                        start_pos=chunk_start,
                        end_pos=chunk_end,
                        index=chunk_index
                    ))
                    chunk_index += 1
                
                # Start new chunk
                current_chunk_sentences = [sentence]
                current_length = sent_len
            else:
                current_chunk_sentences.append(sentence)
                current_length += sent_len + (1 if len(current_chunk_sentences) > 1 else 0)
        
        # Add final chunk
        if current_chunk_sentences:
            chunk_text = ' '.join(current_chunk_sentences)
            chunk_start = start_pos + paragraph.find(current_chunk_sentences[0])
            chunk_end = chunk_start + len(chunk_text)
            
            chunks.append(Chunk(
                content=chunk_text,
                start_pos=chunk_start,
                end_pos=chunk_end,
                index=chunk_index
            ))
        
        return chunks
    
    def _apply_overlap(self, chunks: List[Chunk]) -> List[Chunk]:
        """Apply overlap between chunks.
        
        Adds text from the end of the previous chunk to the beginning
        of the current chunk to maintain context across chunk boundaries.
        """
        if not chunks or self.chunk_overlap <= 0:
            return chunks
        
        result = [chunks[0]]
        
        for i in range(1, len(chunks)):
            prev_chunk = result[-1]
            current_chunk = chunks[i]
            
            # Get overlap text from previous chunk
            overlap_text = self._get_overlap_text(prev_chunk.content)
            
            if overlap_text:
                # Prepend overlap to current chunk
                new_content = overlap_text + ' ' + current_chunk.content
                new_start = max(0, current_chunk.start_pos - len(overlap_text) - 1)
                
                result.append(Chunk(
                    content=new_content,
                    start_pos=new_start,
                    end_pos=current_chunk.end_pos,
                    index=current_chunk.index
                ))
            else:
                result.append(current_chunk)
        
        return result
    
    def _get_overlap_text(self, text: str) -> str:
        """Get overlap text from the end of a chunk."""
        if len(text) <= self.chunk_overlap:
            return text
        
        # Try to find a sentence boundary within overlap range
        overlap_region = text[-self.chunk_overlap:]
        
        # Find the first sentence start in the overlap region
        sentences = self._split_sentences(overlap_region)
        if len(sentences) > 1:
            # Return all but the last sentence
            return ' '.join(sentences[:-1])
        
        # No sentence boundary found, return overlap region
        return overlap_region
    
    def chunk_with_context(
        self,
        text: str,
        context_prefix: Optional[str] = None
    ) -> List[Chunk]:
        """Chunk text with optional context prefix added to each chunk.
        
        Useful for adding document-level context (title, summary) to each chunk.
        
        Args:
            text: Text to chunk
            context_prefix: Optional prefix to add to each chunk
            
        Returns:
            List of chunks with context
        """
        chunks = self.chunk(text)
        
        if not context_prefix:
            return chunks
        
        adjusted_size = self.chunk_size - len(context_prefix) - 1
        if adjusted_size < 100:
            # Context prefix too long, skip it
            return chunks
        
        # Re-chunk with adjusted size
        original_size = self.chunk_size
        self.chunk_size = adjusted_size
        chunks = self.chunk(text)
        self.chunk_size = original_size
        
        # Add prefix to each chunk
        result = []
        for chunk in chunks:
            new_content = context_prefix + '\n' + chunk.content
            result.append(Chunk(
                content=new_content,
                start_pos=chunk.start_pos,
                end_pos=chunk.end_pos,
                index=chunk.index
            ))
        
        return result


class RecursiveSemanticChunker(SemanticChunker):
    """A more aggressive chunker that recursively splits content.
    
    First tries to split by paragraphs, then by sentences within paragraphs,
    then by clauses, and finally by words if necessary.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        separators: Optional[List[str]] = None
    ):
        """Initialize the recursive semantic chunker.
        
        Args:
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            separators: List of separator patterns to try in order
        """
        super().__init__(chunk_size, chunk_overlap)
        
        self.separators = separators or [
            r'\n\s*\n',  # Paragraphs
            r'(?<=[.!?])\s+(?=[A-Z])',  # Sentences
            r'(?<=[:;])\s+',  # Clauses
            r'\s+',  # Words
        ]
    
    def chunk(self, text: str) -> List[Chunk]:
        """Recursively split text using separators."""
        if not text.strip():
            return []
        
        # Normalize
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        return self._recursive_split(text, 0, 0, self.separators.copy())
    
    def _recursive_split(
        self,
        text: str,
        start_pos: int,
        start_index: int,
        separators: List[str]
    ) -> List[Chunk]:
        """Recursively split text using available separators."""
        # If text fits in chunk size, return as single chunk
        if len(text) <= self.chunk_size:
            return [Chunk(
                content=text,
                start_pos=start_pos,
                end_pos=start_pos + len(text),
                index=start_index
            )]
        
        # No more separators, force split
        if not separators:
            return self._force_split(text, start_pos, start_index)
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        # Split by current separator
        parts = re.split(separator, text)
        
        chunks = []
        current_index = start_index
        current_pos = start_pos
        
        for part in parts:
            if not part.strip():
                current_pos += len(part)
                continue
            
            part_start = text.find(part, current_pos - start_pos)
            if part_start != -1:
                part_start += start_pos
            else:
                part_start = current_pos
            
            if len(part) <= self.chunk_size:
                # Part fits, add directly
                chunks.append(Chunk(
                    content=part,
                    start_pos=part_start,
                    end_pos=part_start + len(part),
                    index=current_index
                ))
                current_index += 1
            else:
                # Part too big, recurse with remaining separators
                sub_chunks = self._recursive_split(
                    part, part_start, current_index, remaining_separators
                )
                chunks.extend(sub_chunks)
                current_index += len(sub_chunks)
            
            current_pos = part_start + len(part)
        
        # Apply overlap
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks)
        
        return chunks
    
    def _force_split(
        self,
        text: str,
        start_pos: int,
        start_index: int
    ) -> List[Chunk]:
        """Force split text at chunk_size boundaries."""
        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunk_text = text[i:i + self.chunk_size]
            chunks.append(Chunk(
                content=chunk_text,
                start_pos=start_pos + i,
                end_pos=start_pos + min(i + self.chunk_size, len(text)),
                index=start_index + i // self.chunk_size
            ))
        return chunks


def create_chunker(
    chunk_size: int = 1000,
    chunk_overlap: int = 100,
    recursive: bool = False
) -> SemanticChunker:
    """Factory function to create a chunker.
    
    Args:
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks
        recursive: Whether to use recursive chunking
        
    Returns:
        Configured chunker instance
    """
    if recursive:
        return RecursiveSemanticChunker(chunk_size, chunk_overlap)
    return SemanticChunker(chunk_size, chunk_overlap)
