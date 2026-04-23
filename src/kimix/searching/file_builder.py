from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


class FileReader:
    """Recursively scan text files under given paths and maintain a JSON mapping
    of relative file paths to SHA-256 content hashes.
    """

    __slots__ = ("paths", "output_path", "_mapping", "_max_workers")

    _HASH_CHUNK = 262_144  # 256 KB

    def __init__(self, paths: list[Path], output_path: Path) -> None:
        self.paths = [Path(p).resolve() for p in paths]
        self.output_path = Path(output_path).resolve()
        self._max_workers = min(32, (os.cpu_count() or 1) + 4)
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
                chunk = f.read(self._HASH_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _process_file(self, rel: str, path: Path) -> tuple[str, str] | None:
        """Single-pass text check + SHA-256 hash.

        Returns ``(rel, hex_hash)`` for text files, or ``None`` for binary
        or unreadable files.
        """
        try:
            h = hashlib.sha256()
            with path.open("rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return None
                h.update(chunk)
                while True:
                    chunk = f.read(self._HASH_CHUNK)
                    if not chunk:
                        break
                    h.update(chunk)
            return rel, h.hexdigest()
        except OSError:
            return None

    def _collect_files(self) -> list[tuple[str, Path]]:
        """Gather all candidate *(rel_path, abs_path)* pairs."""
        files: list[tuple[str, Path]] = []
        for root in self.paths:
            if not root.exists():
                continue
            if root.is_file():
                files.append((root.name, root))
                continue
            for file_path in root.rglob("*"):
                if file_path.is_file():
                    rel = str(file_path.relative_to(root)).replace("\\", "/")
                    files.append((rel, file_path))
        return files

    def _scan(self) -> dict[str, str]:
        """Recursively scan paths and return {relative_path: hash}."""
        files = self._collect_files()
        mapping: dict[str, str] = {}
        if not files:
            return mapping

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [
                executor.submit(self._process_file, rel, path)
                for rel, path in files
            ]
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    rel, hash_val = result
                    mapping[rel] = hash_val
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
