"""
Project Analyzer - Gitignore-aware file traversal and analysis preparation.
"""

import os
import re
from pathlib import Path
from fnmatch import fnmatch
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class FileInfo:
    """Information about a project file."""
    path: str
    relative_path: str
    size: int
    lines: int
    language: str
    extension: str
    is_binary: bool = False


class GitignoreParser:
    """Parse and match .gitignore patterns."""
    
    # Common patterns to always ignore
    DEFAULT_IGNORES = {
        '.git', '.svn', '.hg',  # Version control
        '__pycache__', '.pytest_cache', '.mypy_cache',  # Python
        'node_modules', '.npm', '.yarn',  # Node.js
        '.venv', 'venv', 'env', '.env',  # Virtual environments
        'dist', 'build', 'target', 'out',  # Build outputs
        '.idea', '.vscode', '.vs',  # IDE
        '.DS_Store', 'Thumbs.db',  # OS files
        '*.log', '*.tmp', '*.temp', '*.swp', '*.swo',  # Temp files
        '*.pyc', '*.pyo', '*.pyd', '*.so', '*.dll', '*.exe',  # Compiled
        '*.min.js', '*.min.css', '*.map',  # Minified files
        'coverage', '.coverage', 'htmlcov',  # Coverage
        '.tox', '.nox',  # Testing environments
        '*.egg-info', '.eggs',  # Package metadata
    }
    
    def __init__(self, gitignore_path: Optional[Path] = None):
        self.patterns = []
        self.negations = []
        self.base_path = gitignore_path.parent if gitignore_path else None
        
        if gitignore_path and gitignore_path.exists():
            self._parse_gitignore(gitignore_path)
    
    def _parse_gitignore(self, path: Path):
        """Parse .gitignore file and extract patterns."""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Handle negation patterns
                if line.startswith('!'):
                    self.negations.append(line[1:])
                else:
                    self.patterns.append(line)
    
    def is_ignored(self, file_path: str, is_dir: bool = False) -> bool:
        """Check if a file path matches any gitignore pattern."""
        # Check default ignores first
        path_parts = file_path.replace('\\', '/').split('/')
        
        for part in path_parts:
            if part in self.DEFAULT_IGNORES:
                return True
            # Check wildcard patterns in defaults
            for pattern in self.DEFAULT_IGNORES:
                if pattern.startswith('*') and fnmatch(part, pattern):
                    return True
        
        # Get relative path from gitignore location
        if self.base_path:
            try:
                rel_path = os.path.relpath(file_path, self.base_path)
            except ValueError:
                rel_path = file_path
        else:
            rel_path = file_path
        
        rel_path = rel_path.replace('\\', '/')
        
        # Check negations first (they override ignores)
        for pattern in self.negations:
            if self._match_pattern(rel_path, pattern, is_dir):
                return False
        
        # Check ignore patterns
        for pattern in self.patterns:
            if self._match_pattern(rel_path, pattern, is_dir):
                return True
        
        return False
    
    def _match_pattern(self, file_path: str, pattern: str, is_dir: bool) -> bool:
        """Check if file_path matches the given pattern."""
        pattern = pattern.replace('\\', '/')
        
        # Handle directory-specific patterns
        if pattern.endswith('/'):
            if not is_dir:
                return False
            pattern = pattern[:-1]
        
        # Handle anchored patterns (starting with /)
        if pattern.startswith('/'):
            pattern = pattern[1:]
            matches = fnmatch(file_path, pattern) or fnmatch(file_path, pattern + '/*')
        else:
            # Unanchored patterns match at any level
            parts = file_path.split('/')
            matches = False
            for i in range(len(parts)):
                subpath = '/'.join(parts[i:])
                if fnmatch(subpath, pattern) or fnmatch(subpath, pattern + '/*'):
                    matches = True
                    break
                # Also check basename
                if i == len(parts) - 1 and fnmatch(parts[i], pattern):
                    matches = True
                    break
        
        return matches


class ProjectAnalyzer:
    """Analyze project structure with gitignore support."""
    
    # Language detection by extension
    LANGUAGE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.r': 'r',
        '.m': 'objective-c',
        '.mm': 'objective-cpp',
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.ps1': 'powershell',
        '.pl': 'perl',
        '.lua': 'lua',
        '.groovy': 'groovy',
        '.dart': 'dart',
        '.elm': 'elm',
        '.erl': 'erlang',
        '.ex': 'elixir',
        '.fs': 'fsharp',
        '.hs': 'haskell',
        '.jl': 'julia',
        '.clj': 'clojure',
        '.coffee': 'coffeescript',
        '.fsx': 'fsharp',
        '.ml': 'ocaml',
        '.pas': 'pascal',
        '.scm': 'scheme',
        '.lisp': 'lisp',
        '.vim': 'vimscript',
        '.html': 'html',
        '.htm': 'html',
        '.xml': 'xml',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.less': 'less',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'ini',
        '.conf': 'conf',
        '.md': 'markdown',
        '.rst': 'restructuredtext',
        '.sql': 'sql',
        '.graphql': 'graphql',
        '.proto': 'protobuf',
        '.dockerfile': 'dockerfile',
        '.makefile': 'makefile',
        '.cmake': 'cmake',
    }
    
    # Binary file extensions to skip
    BINARY_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
        '.exe', '.dll', '.so', '.dylib', '.bin',
        '.ttf', '.otf', '.woff', '.woff2', '.eot',
        '.sqlite', '.db', '.mdb',
    }
    
    # Config file patterns
    CONFIG_PATTERNS = {
        'package.json', 'requirements.txt', 'Cargo.toml', 'pom.xml', 'build.gradle',
        'CMakeLists.txt', 'Makefile', 'Dockerfile', 'docker-compose.yml',
        '.gitignore', '.editorconfig', 'tsconfig.json', 'setup.py', 'setup.cfg',
        'pyproject.toml', 'Gemfile', 'composer.json', 'go.mod', 'go.sum',
    }
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.gitignore_parser = None
        self._load_gitignore()
    
    def _load_gitignore(self):
        """Load .gitignore file from project root."""
        gitignore_path = self.project_path / '.gitignore'
        if gitignore_path.exists():
            self.gitignore_parser = GitignoreParser(gitignore_path)
        else:
            # Create parser with defaults only
            self.gitignore_parser = GitignoreParser()
            self.gitignore_parser.base_path = self.project_path
    
    def detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        return self.LANGUAGE_MAP.get(ext, 'text')
    
    def is_binary_file(self, file_path: str) -> bool:
        """Check if file is binary based on extension."""
        ext = Path(file_path).suffix.lower()
        if ext in self.BINARY_EXTENSIONS:
            return True
        
        # Try to detect binary by reading first bytes
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                if b'\x00' in chunk:
                    return True
        except:
            pass
        
        return False
    
    def is_config_file(self, file_path: str) -> bool:
        """Check if file is a configuration file."""
        name = Path(file_path).name
        return name in self.CONFIG_PATTERNS
    
    def traverse(self, max_file_size: int = 1024 * 1024) -> List[FileInfo]:
        """
        Recursively traverse project directory respecting .gitignore.
        
        Args:
            max_file_size: Maximum file size in bytes (default 1MB)
        
        Returns:
            List of FileInfo objects for analyzable files
        """
        files = []
        
        for root, dirs, filenames in os.walk(self.project_path):
            root_path = Path(root)
            
            # Filter out ignored directories
            dirs[:] = [
                d for d in dirs 
                if not self.gitignore_parser.is_ignored(str(root_path / d), is_dir=True)
            ]
            
            for filename in filenames:
                file_path = root_path / filename
                rel_path = file_path.relative_to(self.project_path)
                rel_path_str = str(rel_path).replace('\\', '/')
                
                # Skip ignored files
                if self.gitignore_parser.is_ignored(str(file_path)):
                    continue
                
                # Skip binary files
                if self.is_binary_file(str(file_path)):
                    continue
                
                # Skip files that are too large
                try:
                    size = file_path.stat().st_size
                    if size > max_file_size:
                        continue
                except:
                    continue
                
                # Count lines
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = content.count('\n') + 1
                except:
                    continue
                
                # Detect language
                language = self.detect_language(str(file_path))
                extension = Path(filename).suffix.lower()
                
                file_info = FileInfo(
                    path=str(file_path),
                    relative_path=rel_path_str,
                    size=size,
                    lines=lines,
                    language=language,
                    extension=extension,
                    is_binary=False
                )
                files.append(file_info)
        
        return files
    
    def group_by_directory(self, files: List[FileInfo]) -> Dict[str, List[FileInfo]]:
        """Group files by their parent directory."""
        groups = {}
        for f in files:
            dir_path = str(Path(f.relative_path).parent)
            if dir_path == '.':
                dir_path = 'root'
            if dir_path not in groups:
                groups[dir_path] = []
            groups[dir_path].append(f)
        return groups
    
    def group_by_language(self, files: List[FileInfo]) -> Dict[str, List[FileInfo]]:
        """Group files by programming language."""
        groups = {}
        for f in files:
            lang = f.language
            if lang not in groups:
                groups[lang] = []
            groups[lang].append(f)
        return groups
    
    def get_project_structure(self) -> Dict:
        """Get overall project structure summary."""
        files = self.traverse()
        
        by_language = self.group_by_language(files)
        by_directory = self.group_by_directory(files)
        
        # Identify entry points
        entry_points = []
        for f in files:
            name = Path(f.path).name.lower()
            if name in {'main.py', 'app.py', 'server.py', 'index.js', 'main.js', 
                       'app.js', 'main.go', 'program.cs', 'main.java', 'main.rs'}:
                entry_points.append(f.relative_path)
        
        # Identify config files
        config_files = [f.relative_path for f in files if self.is_config_file(f.path)]
        
        return {
            'total_files': len(files),
            'total_lines': sum(f.lines for f in files),
            'languages': {lang: len(files) for lang, files in by_language.items()},
            'directories': list(by_directory.keys()),
            'entry_points': entry_points,
            'config_files': config_files,
            'files': files
        }
    
    def create_batches(self, files: List[FileInfo], max_batch_size: int = 5, 
                       max_batch_lines: int = 500) -> List[List[FileInfo]]:
        """
        Create batches of files for analysis.
        
        Groups files by directory and respects size limits.
        """
        by_dir = self.group_by_directory(files)
        batches = []
        
        for dir_path, dir_files in by_dir.items():
            current_batch = []
            current_lines = 0
            
            for f in sorted(dir_files, key=lambda x: x.lines, reverse=True):
                if len(current_batch) >= max_batch_size or current_lines + f.lines > max_batch_lines:
                    if current_batch:
                        batches.append(current_batch)
                    current_batch = [f]
                    current_lines = f.lines
                else:
                    current_batch.append(f)
                    current_lines += f.lines
            
            if current_batch:
                batches.append(current_batch)
        
        return batches


def get_language_priority(language: str) -> int:
    """Get priority for language ordering (lower = higher priority)."""
    priorities = {
        'python': 1,
        'javascript': 2,
        'typescript': 3,
        'java': 4,
        'go': 5,
        'rust': 6,
        'cpp': 7,
        'c': 8,
        'csharp': 9,
        'ruby': 10,
        'php': 11,
    }
    return priorities.get(language, 100)
