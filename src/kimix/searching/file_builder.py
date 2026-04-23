from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class FileReader:
    """Recursively scan text files under given paths and maintain a JSON mapping
    of relative file paths to SHA-256 content hashes.
    """

    def __init__(self, paths: list[Path], output_path: Path) -> None:
        self.paths = [Path(p).resolve() for p in paths]
        self.output_path = Path(output_path).resolve()
        self._mapping: dict[str, str] = {}
        self._build()

    def _is_text_file(self, path: Path) -> bool:
        """Heuristic to determine whether a file is a text file."""
        try:
            with path.open("rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return False
            with path.open("r", encoding="utf-8", errors="replace") as f:
                f.read(1)
            return True
        except (OSError, UnicodeDecodeError):
            return False

    def _hash_file(self, path: Path) -> str:
        """Compute SHA-256 hash of a file's contents."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _scan(self) -> dict[str, str]:
        """Recursively scan paths and return {relative_path: hash}."""
        mapping: dict[str, str] = {}
        for root in self.paths:
            if not root.exists():
                continue
            if root.is_file() and self._is_text_file(root):
                rel = root.name
                mapping[rel] = self._hash_file(root)
                continue
            for file_path in root.rglob("*"):
                if file_path.is_file() and self._is_text_file(file_path):
                    rel = str(file_path.relative_to(root)).replace("\\", "/")
                    mapping[rel] = self._hash_file(file_path)
        return mapping

    def _build(self) -> None:
        """Initial build: scan and write JSON."""
        self._mapping = self._scan()
        self._write()

    def _write(self) -> None:
        """Persist the current mapping to JSON."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as f:
            json.dump(self._mapping, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def update(self) -> None:
        """Re-scan directories and rewrite JSON if any file was created,
        deleted, or modified.
        """
        current = self._scan()
        if current != self._mapping:
            self._mapping = current
            self._write()
