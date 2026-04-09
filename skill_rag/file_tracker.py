"""File tracker for incremental indexing.

Tracks file modification times and document ID mappings
to enable efficient incremental re-indexing.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FileIndexEntry:
    """Entry tracking a single file's index state."""
    path: str
    mtime: float
    content_hash: str
    doc_ids: List[str] = field(default_factory=list)
    indexed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    chunk_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileIndexEntry":
        """Create from dictionary."""
        return cls(**data)


class FileTracker:
    """Tracks file indexing state for incremental updates.
    
    Maintains a mapping of file paths to their:
    - Modification time (mtime)
    - Content hash
    - Document IDs (chunks) in the vector store
    
    This enables efficient incremental indexing by:
    - Skipping files that haven't changed
    - Deleting old chunks when files are updated
    - Removing chunks for deleted files
    """
    
    def __init__(self, index_path: Optional[Path] = None):
        """Initialize the file tracker.
        
        Args:
            index_path: Path to store the index JSON file.
                         If None, uses in-memory tracking only.
        """
        self.index_path = index_path
        self._files: Dict[str, FileIndexEntry] = {}
        
        if index_path:
            self._load()
    
    def _load(self) -> None:
        """Load the file index from disk."""
        if not self.index_path or not self.index_path.exists():
            return
        
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._files = {
                path: FileIndexEntry.from_dict(entry)
                for path, entry in data.get("files", {}).items()
            }
            logger.debug(f"Loaded file tracker with {len(self._files)} entries")
        except Exception as e:
            logger.warning(f"Failed to load file tracker: {e}")
            self._files = {}
    
    def save(self) -> None:
        """Save the file index to disk."""
        if not self.index_path:
            return
        
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": 1,
                "files": {
                    path: entry.to_dict()
                    for path, entry in self._files.items()
                }
            }
            
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved file tracker with {len(self._files)} entries")
        except Exception as e:
            logger.warning(f"Failed to save file tracker: {e}")
    
    def get_entry(self, file_path: Path) -> Optional[FileIndexEntry]:
        """Get the index entry for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            FileIndexEntry if found, None otherwise
        """
        return self._files.get(str(file_path))
    
    def get_mtime(self, file_path: Path) -> Optional[float]:
        """Get the stored modification time for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Modification time timestamp or None
        """
        entry = self._files.get(str(file_path))
        return entry.mtime if entry else None
    
    def needs_update(self, file_path: Path, current_hash: str) -> bool:
        """Check if a file needs to be re-indexed.
        
        Args:
            file_path: Path to the file
            current_hash: Current content hash of the file
            
        Returns:
            True if file needs re-indexing
        """
        entry = self._files.get(str(file_path))
        if not entry:
            return True
        
        # Check if content hash changed
        if entry.content_hash != current_hash:
            return True
        
        # Also check mtime as a quick filter
        try:
            current_mtime = file_path.stat().st_mtime
            if entry.mtime != current_mtime:
                # mtime changed, verify with hash
                return True
        except (OSError, FileNotFoundError):
            return True
        
        return False
    
    def update_file(
        self,
        file_path: Path,
        content_hash: str,
        doc_ids: List[str]
    ) -> List[str]:
        """Update or add a file entry.
        
        Args:
            file_path: Path to the file
            content_hash: Content hash of the file
            doc_ids: List of document IDs (chunks) for this file
            
        Returns:
            List of old document IDs that should be deleted
        """
        path_str = str(file_path)
        old_ids: List[str] = []
        
        # Get old IDs if updating existing entry
        if path_str in self._files:
            old_ids = self._files[path_str].doc_ids
        
        # Get current mtime
        try:
            mtime = file_path.stat().st_mtime
        except (OSError, FileNotFoundError):
            mtime = 0.0
        
        # Create new entry
        self._files[path_str] = FileIndexEntry(
            path=path_str,
            mtime=mtime,
            content_hash=content_hash,
            doc_ids=doc_ids,
            chunk_count=len(doc_ids)
        )
        
        # Return IDs that are no longer valid
        return [oid for oid in old_ids if oid not in doc_ids]
    
    def remove_file(self, file_path: Path) -> List[str]:
        """Remove a file entry and return its document IDs.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of document IDs to delete from the vector store
        """
        path_str = str(file_path)
        entry = self._files.pop(path_str, None)
        
        if entry:
            logger.debug(f"Removed file entry: {path_str}")
            return entry.doc_ids
        
        return []
    
    def get_all_doc_ids(self) -> Set[str]:
        """Get all tracked document IDs.
        
        Returns:
            Set of all document IDs across all files
        """
        all_ids = set()
        for entry in self._files.values():
            all_ids.update(entry.doc_ids)
        return all_ids
    
    def get_doc_ids_for_file(self, file_path: Path) -> List[str]:
        """Get document IDs for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of document IDs
        """
        entry = self._files.get(str(file_path))
        return entry.doc_ids if entry else []
    
    def get_chunk_count_for_file(self, file_path: Path) -> int:
        """Get chunk count for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Number of chunks for this file (0 if not tracked)
        """
        entry = self._files.get(str(file_path))
        return entry.chunk_count if entry else 0
    
    def get_stale_files(self, current_files: Set[Path]) -> Set[Path]:
        """Get files that are no longer present.
        
        Args:
            current_files: Set of currently existing file paths
            
        Returns:
            Set of file paths that are tracked but no longer exist
        """
        tracked = {Path(p) for p in self._files.keys()}
        return tracked - current_files
    
    def cleanup_stale(self, current_files: Set[Path]) -> List[str]:
        """Remove stale entries and return their document IDs.
        
        Args:
            current_files: Set of currently existing file paths
            
        Returns:
            List of document IDs to delete
        """
        stale = self.get_stale_files(current_files)
        removed_ids = []
        
        for file_path in stale:
            ids = self.remove_file(file_path)
            removed_ids.extend(ids)
            logger.info(f"Cleaned up stale file: {file_path}")
        
        return removed_ids
    
    def clear(self) -> None:
        """Clear all tracked entries."""
        self._files.clear()
        if self.index_path and self.index_path.exists():
            try:
                self.index_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to remove file tracker: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the tracked files.
        
        Returns:
            Dict with statistics
        """
        total_files = len(self._files)
        total_chunks = sum(e.chunk_count for e in self._files.values())
        
        return {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "avg_chunks_per_file": total_chunks / total_files if total_files > 0 else 0,
            "index_path": str(self.index_path) if self.index_path else None
        }


def compute_file_hash(file_path: Path) -> str:
    """Compute a hash for a file's content.
    
    Uses MD5 for speed; suitable for detecting changes, not security.
    
    Args:
        file_path: Path to the file
        
    Returns:
        MD5 hash of file content, or empty string on error
    """
    import hashlib
    
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        logger.warning(f"Failed to hash file {file_path}: {e}")
        return ""
