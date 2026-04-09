"""Code file loader with semantic chunking for programming languages."""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
import logging

from .document_loaders import BaseLoader, Document

logger = logging.getLogger(__name__)


@dataclass
class CodeBlock:
    """Represents a semantic block of code (function, class, etc.)."""
    name: str
    type: str  # 'function', 'class', 'method', 'import', 'comment', 'other'
    content: str
    start_line: int
    end_line: int
    parent: Optional[str] = None  # Parent class name for methods


class LanguageParser(ABC):
    """Base class for language-specific parsers."""
    
    # File extensions this parser handles
    extensions: List[str] = []
    
    # Patterns for detecting code structures
    patterns: Dict[str, str] = {}
    
    @abstractmethod
    def parse(self, content: str, file_path: Path) -> List[CodeBlock]:
        """Parse code content into semantic blocks.
        
        Args:
            content: Source code content
            file_path: Path to the file (for context)
            
        Returns:
            List of CodeBlock objects
        """
        pass
    
    def get_line_number(self, content: str, position: int) -> int:
        """Get line number for a character position."""
        return content[:position].count('\n') + 1


class PythonParser(LanguageParser):
    """Parser for Python files."""
    
    extensions = ['.py', '.pyw']
    
    # Regex patterns for Python
    patterns = {
        'function': r'^(\s*)def\s+(\w+)\s*\(',
        'class': r'^(\s*)class\s+(\w+)(?:\s*\(|\s*:)', 
        'method': r'^(\s*)def\s+(\w+)\s*\(self',
        'decorator': r'^\s*@(\w+)',
        'docstring': r'^(\s*)("""|\'\'\')',
        'import': r'^(?:from\s+\S+\s+)?import\s+',
        'comment': r'^\s*#',
    }
    
    def parse(self, content: str, file_path: Path) -> List[CodeBlock]:
        """Parse Python code into semantic blocks."""
        blocks = []
        lines = content.split('\n')
        current_class = None
        current_block = None
        block_start = 0
        block_content = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Skip empty lines at start of potential block
            if not stripped and not block_content:
                i += 1
                continue
            
            # Check for class definition
            class_match = re.match(self.patterns['class'], line)
            if class_match:
                # Save previous block if exists
                if block_content:
                    blocks.append(self._create_block(
                        block_content, block_start, i - 1, 
                        'function' if current_class else 'other',
                        file_path
                    ))
                
                current_class = class_match.group(2)
                block_start = i
                block_content = [line]
                
                # Collect class body
                class_indent = len(class_match.group(1))
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    if next_line.strip() and not next_line.startswith(' ' * (class_indent + 1)) and not next_line.startswith('\t'):
                        break
                    block_content.append(next_line)
                    i += 1
                
                blocks.append(self._create_block(
                    block_content, block_start, i - 1, 'class', file_path
                ))
                block_content = []
                current_class = None
                continue
            
            # Check for function definition
            func_match = re.match(self.patterns['function'], line)
            if func_match:
                # Save previous block if exists
                if block_content:
                    blocks.append(self._create_block(
                        block_content, block_start, i - 1, 'other', file_path
                    ))
                
                func_name = func_match.group(2)
                is_method = 'self' in line or 'cls' in line
                block_type = 'method' if (is_method and current_class) else 'function'
                
                block_start = i
                block_content = [line]
                
                # Collect function body
                base_indent = len(func_match.group(1))
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    if next_line.strip() and not next_line.startswith(' ' * (base_indent + 1)) and not next_line.startswith('\t'):
                        break
                    block_content.append(next_line)
                    i += 1
                
                blocks.append(CodeBlock(
                    name=func_name,
                    type=block_type,
                    content='\n'.join(block_content),
                    start_line=block_start + 1,
                    end_line=i,
                    parent=current_class if block_type == 'method' else None
                ))
                block_content = []
                continue
            
            # Check for imports at module level
            if re.match(self.patterns['import'], line) and not block_content:
                import_start = i
                import_lines = []
                while i < len(lines) and (re.match(self.patterns['import'], lines[i]) or not lines[i].strip()):
                    import_lines.append(lines[i])
                    i += 1
                
                if import_lines:
                    blocks.append(CodeBlock(
                        name='imports',
                        type='import',
                        content='\n'.join(import_lines).strip(),
                        start_line=import_start + 1,
                        end_line=i
                    ))
                continue
            
            # Collect other content
            if stripped:
                if not block_content:
                    block_start = i
                block_content.append(line)
            
            i += 1
        
        # Handle remaining content
        if block_content:
            blocks.append(self._create_block(
                block_content, block_start, len(lines) - 1, 'other', file_path
            ))
        
        return blocks
    
    def _create_block(self, lines: List[str], start: int, end: int, 
                     block_type: str, file_path: Path) -> CodeBlock:
        """Create a CodeBlock from lines."""
        content = '\n'.join(lines).strip()
        # Extract name from first line if possible
        first_line = lines[0].strip()
        name = 'unnamed'
        
        if block_type == 'class':
            match = re.match(self.patterns['class'], lines[0])
            if match:
                name = match.group(2)
        elif block_type in ('function', 'method'):
            match = re.match(self.patterns['function'], lines[0])
            if match:
                name = match.group(2)
        
        return CodeBlock(
            name=name,
            type=block_type,
            content=content,
            start_line=start + 1,
            end_line=end + 1
        )


class JavaScriptParser(LanguageParser):
    """Parser for JavaScript/TypeScript files."""
    
    extensions = ['.js', '.jsx', '.ts', '.tsx', '.mjs']
    
    patterns = {
        'function': r'(?:^|\s)(?:async\s+)?function\s+(\w+)',
        'arrow_func': r'(?:^|\s)(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(',
        'class': r'(?:^|\s)class\s+(\w+)',
        'method': r'(?:^|\s)(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{',
        'import': r'^(?:import|export)\b',
        'comment': r'^\s*//',
    }
    
    def parse(self, content: str, file_path: Path) -> List[CodeBlock]:
        """Parse JavaScript/TypeScript code into semantic blocks."""
        blocks = []
        lines = content.split('\n')
        current_class = None
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                i += 1
                continue
            
            # Class definition
            class_match = re.search(self.patterns['class'], line)
            if class_match and '{' in line:
                block_start = i
                block_content, end_line = self._extract_block(lines, i, '{', '}')
                
                blocks.append(CodeBlock(
                    name=class_match.group(1),
                    type='class',
                    content='\n'.join(block_content),
                    start_line=block_start + 1,
                    end_line=end_line + 1
                ))
                current_class = class_match.group(1)
                i = end_line + 1
                continue
            
            # Function definition
            func_match = re.search(self.patterns['function'], line)
            if func_match and '{' in line:
                block_start = i
                block_content, end_line = self._extract_block(lines, i, '{', '}')
                
                blocks.append(CodeBlock(
                    name=func_match.group(1),
                    type='function',
                    content='\n'.join(block_content),
                    start_line=block_start + 1,
                    end_line=end_line + 1,
                    parent=current_class
                ))
                i = end_line + 1
                continue
            
            # Arrow function assignment
            arrow_match = re.search(self.patterns['arrow_func'], line)
            if arrow_match:
                block_start = i
                # Find where the arrow function ends
                brace_count = 0
                in_arrow = False
                j = i
                while j < len(lines):
                    curr = lines[j]
                    if '=>' in curr:
                        in_arrow = True
                    if in_arrow:
                        brace_count += curr.count('{') - curr.count('}')
                        if brace_count <= 0 and '{' in curr:
                            break
                        if '{' not in curr and curr.strip().endswith(';'):
                            break
                    j += 1
                
                block_content = lines[i:j+1]
                blocks.append(CodeBlock(
                    name=arrow_match.group(1),
                    type='function',
                    content='\n'.join(block_content),
                    start_line=block_start + 1,
                    end_line=j + 1
                ))
                i = j + 1
                continue
            
            # Imports
            if re.match(self.patterns['import'], line):
                import_start = i
                import_lines = []
                while i < len(lines) and (re.match(self.patterns['import'], lines[i]) or not lines[i].strip()):
                    import_lines.append(lines[i])
                    i += 1
                
                if import_lines:
                    blocks.append(CodeBlock(
                        name='imports',
                        type='import',
                        content='\n'.join(import_lines).strip(),
                        start_line=import_start + 1,
                        end_line=i
                    ))
                continue
            
            i += 1
        
        return blocks
    
    def _extract_block(self, lines: List[str], start: int, 
                      open_char: str, close_char: str) -> Tuple[List[str], int]:
        """Extract a balanced block of code."""
        block = [lines[start]]
        brace_count = lines[start].count(open_char) - lines[start].count(close_char)
        i = start + 1
        
        while i < len(lines) and brace_count > 0:
            block.append(lines[i])
            brace_count += lines[i].count(open_char) - lines[i].count(close_char)
            i += 1
        
        return block, i - 1


class GenericCodeParser(LanguageParser):
    """Generic parser for C-style languages (Java, C, C++, Go, Rust)."""
    
    extensions = ['.java', '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', 
                  '.go', '.rs', '.cs', '.kt', '.scala']
    
    patterns = {
        # Function pattern handles:
        # - C-style: int func() { } or int func();
        # - Rust/Go: fn func() -> Type { } or fn func() -> Type;
        # - Modifiers: pub fn, async fn, etc.
        'function': r'(?:^|\s)(?:\w+\s+)*(?:fn|func)?\s*(\w+)\s*\([^)]*\)\s*(?:->\s*\w+\s*)?(?:\{|;)',
        'class': r'(?:^|\s)(?:class|struct|interface)\s+(\w+)',
        'namespace': r'(?:^|\s)namespace\s+(\w+)',
        'import': r'^(?:#include|import|using|package|extern)\b',
        'comment': r'^\s*(?://|/\*|\*)',
    }
    
    def parse(self, content: str, file_path: Path) -> List[CodeBlock]:
        """Parse C-style code into semantic blocks."""
        blocks = []
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped:
                i += 1
                continue
            
            # Preprocessor directives / imports
            if re.match(self.patterns['import'], line):
                import_start = i
                import_lines = []
                while i < len(lines) and (re.match(self.patterns['import'], lines[i]) or not lines[i].strip()):
                    import_lines.append(lines[i])
                    i += 1
                
                if import_lines:
                    blocks.append(CodeBlock(
                        name='imports',
                        type='import',
                        content='\n'.join(import_lines).strip(),
                        start_line=import_start + 1,
                        end_line=i
                    ))
                continue
            
            # Class/struct definition
            class_match = re.search(self.patterns['class'], line)
            if class_match:
                block_start = i
                block_content, end_line = self._extract_block(lines, i, '{', '}')
                
                blocks.append(CodeBlock(
                    name=class_match.group(1),
                    type='class',
                    content='\n'.join(block_content),
                    start_line=block_start + 1,
                    end_line=end_line + 1
                ))
                i = end_line + 1
                continue
            
            # Function definition or declaration
            func_match = re.search(self.patterns['function'], line)
            if func_match:
                if '{' in line:
                    # Function with body
                    block_start = i
                    block_content, end_line = self._extract_block(lines, i, '{', '}')
                    
                    blocks.append(CodeBlock(
                        name=func_match.group(1),
                        type='function',
                        content='\n'.join(block_content),
                        start_line=block_start + 1,
                        end_line=end_line + 1
                    ))
                    i = end_line + 1
                    continue
                elif ';' in line:
                    # Function declaration (e.g., in header files)
                    blocks.append(CodeBlock(
                        name=func_match.group(1),
                        type='function',
                        content=stripped,
                        start_line=i + 1,
                        end_line=i + 1
                    ))
                    i += 1
                    continue
            
            i += 1
        
        return blocks
    
    def _extract_block(self, lines: List[str], start: int,
                      open_char: str, close_char: str) -> Tuple[List[str], int]:
        """Extract a balanced block of code."""
        block = [lines[start]]
        brace_count = lines[start].count(open_char) - lines[start].count(close_char)
        i = start + 1
        
        # Handle single-line definitions
        if brace_count == 0 and ';' in lines[start]:
            return block, start
        
        while i < len(lines) and brace_count > 0:
            block.append(lines[i])
            brace_count += lines[i].count(open_char) - lines[i].count(close_char)
            i += 1
        
        return block, i - 1


# Registry of parsers
PARSERS: Dict[str, LanguageParser] = {}

def _register_parser(parser_class):
    """Register a parser for its extensions."""
    parser = parser_class()
    for ext in parser_class.extensions:
        PARSERS[ext] = parser

_register_parser(PythonParser)
_register_parser(JavaScriptParser)
_register_parser(GenericCodeParser)


def get_parser(file_path: Path) -> Optional[LanguageParser]:
    """Get the appropriate parser for a file."""
    ext = file_path.suffix.lower()
    return PARSERS.get(ext)


def is_code_file(file_path: Path) -> bool:
    """Check if a file is a supported code file."""
    return file_path.suffix.lower() in PARSERS


class CodeLoader(BaseLoader):
    """Loader for source code files with semantic chunking.
    
    Supports Python (.py), JavaScript/TypeScript (.js, .ts, .jsx, .tsx),
    Java, C/C++, Go, Rust, C#, Kotlin, and Scala files.
    
    Uses language-specific parsers to extract semantic blocks (functions,
    classes, methods) as chunks, preserving code structure.
    
    Args:
        chunk_size: Maximum size of chunks (not used for code, blocks are semantic)
        chunk_overlap: Overlap between chunks (not used for code)
        include_imports: Whether to include import blocks as chunks
        include_comments: Whether to include standalone comment blocks
    """
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.mjs',
                           '.java', '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp',
                           '.go', '.rs', '.cs', '.kt', '.scala', '.pyw'}
    
    def _get_default_pattern(self) -> str:
        """Get default file pattern for code files."""
        return "*.py"  # Default to Python files
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100,
                 include_imports: bool = True, include_comments: bool = False):
        super().__init__(chunk_size, chunk_overlap)
        self.include_imports = include_imports
        self.include_comments = include_comments
    
    def load_file(self, file_path: Path) -> List[Document]:
        """Load a code file and parse into semantic chunks.
        
        Args:
            file_path: Path to the code file
            
        Returns:
            List of Document objects, each representing a semantic code block
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        # Get the appropriate parser
        parser = get_parser(file_path)
        if not parser:
            # Fallback to simple text chunking
            return self._fallback_load(file_path)
        
        # Read file content
        content = self._read_file(file_path)
        
        # Parse into semantic blocks
        blocks = parser.parse(content, file_path)
        
        # Convert blocks to documents
        documents = []
        for block in blocks:
            # Skip import blocks if not included
            if block.type == 'import' and not self.include_imports:
                continue
            
            # Skip comment blocks if not included  
            if block.type == 'comment' and not self.include_comments:
                continue
            
            # Create metadata
            metadata = {
                'source': str(file_path),
                'filename': file_path.name,
                'file_type': 'code',
                'language': self._get_language(file_path),
                'block_type': block.type,
                'block_name': block.name,
                'start_line': block.start_line,
                'end_line': block.end_line,
            }
            
            if block.parent:
                metadata['parent_class'] = block.parent
            
            # Add docstring extraction for functions/classes
            if block.type in ('function', 'method', 'class'):
                docstring = self._extract_docstring(block.content, metadata['language'])
                if docstring:
                    metadata['docstring'] = docstring
            
            documents.append(Document(
                content=block.content,
                metadata=metadata,
                source=str(file_path),
                chunk_index=len(documents),
                start_line=block.start_line,
                end_line=block.end_line
            ))
        
        return documents
    
    def _read_file(self, file_path: Path) -> str:
        """Read file content with encoding detection."""
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        raise ValueError(f"Could not decode file: {file_path}")
    
    def _fallback_load(self, file_path: Path) -> List[Document]:
        """Fallback to simple line-based chunking for unsupported files."""
        content = self._read_file(file_path)
        lines = content.split('\n')
        
        # Group lines into chunks of ~50 lines
        chunk_size = 50
        documents = []
        
        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:i + chunk_size]
            chunk_content = '\n'.join(chunk_lines)
            
            documents.append(Document(
                content=chunk_content,
                metadata={
                    'source': str(file_path),
                    'filename': file_path.name,
                    'file_type': 'code',
                    'language': 'unknown',
                    'block_type': 'chunk',
                },
                source=str(file_path),
                chunk_index=len(documents),
                start_line=i + 1,
                end_line=min(i + chunk_size, len(lines))
            ))
        
        return documents
    
    def _get_language(self, file_path: Path) -> str:
        """Get programming language from file extension."""
        mapping = {
            '.py': 'python', '.pyw': 'python',
            '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript',
            '.ts': 'typescript', '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.c': 'c',
            '.h': 'c', '.hpp': 'cpp',
            '.go': 'go',
            '.rs': 'rust',
            '.cs': 'csharp',
            '.kt': 'kotlin',
            '.scala': 'scala',
        }
        return mapping.get(file_path.suffix.lower(), 'unknown')
    
    def _extract_docstring(self, content: str, language: str) -> Optional[str]:
        """Extract docstring/comment from code block."""
        if language == 'python':
            # Look for triple-quoted strings
            patterns = [
                r'"""(.*?)"""',
                r"'''(.*?)'''"
            ]
            for pattern in patterns:
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    docstring = match.group(1).strip()
                    # Only return if it looks like a docstring (at start or after def/class)
                    lines_before = content[:match.start()].split('\n')
                    if lines_before:
                        last_line = lines_before[-1].strip()
                        if not last_line or last_line.endswith(':') or last_line.startswith('def ') or last_line.startswith('class '):
                            return docstring
        
        elif language in ('javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'csharp', 'kotlin'):
            # Look for Javadoc or block comments
            # Javadoc style: /** ... */
            block_match = re.search(r'/\*\*(.*?)\*/', content, re.DOTALL)
            if block_match:
                # Clean up Javadoc markers
                docstring = block_match.group(1)
                docstring = re.sub(r'^\s*\*\s?', '', docstring, flags=re.MULTILINE)
                return docstring.strip()
            
            # Single-line comments before function
            comment_lines = []
            lines = content.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('//'):
                    comment_lines.append(stripped[2:].strip())
                elif stripped and not stripped.startswith('//'):
                    break
            
            if comment_lines:
                return '\n'.join(comment_lines)
        
        return None


def create_code_loader(chunk_size: int = 1000, chunk_overlap: int = 100,
                      include_imports: bool = True) -> CodeLoader:
    """Create a CodeLoader with default settings.
    
    Args:
        chunk_size: Not used for semantic chunking, kept for API compatibility
        chunk_overlap: Not used for semantic chunking
        include_imports: Whether to include import blocks
        
    Returns:
        Configured CodeLoader instance
    """
    return CodeLoader(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        include_imports=include_imports
    )
