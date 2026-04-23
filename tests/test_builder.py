"""Comprehensive tests for src/kimix/searching/file_builder.py."""

import hashlib
import json
from pathlib import Path

import pytest

from kimix.searching.file_builder import FileReader


class TestIsTextFile:
    """Tests for FileReader._is_text_file heuristic."""

    def test_plain_text_file(self, tmp_path: Path) -> None:
        """A standard UTF-8 text file should be recognised as text."""
        file_path = tmp_path / "hello.txt"
        file_path.write_text("hello world", encoding="utf-8")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        assert reader._is_text_file(file_path) is True

    def test_empty_file_is_text(self, tmp_path: Path) -> None:
        """An empty file should be considered a text file."""
        file_path = tmp_path / "empty.txt"
        file_path.write_text("")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        assert reader._is_text_file(file_path) is True

    def test_binary_with_null_byte(self, tmp_path: Path) -> None:
        """A file containing a null byte in the first chunk is binary."""
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(b"\x00\x01\x02\x03")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        assert reader._is_text_file(file_path) is False

    def test_utf8_bom_text_file(self, tmp_path: Path) -> None:
        """A UTF-8 BOM file should be recognised as text."""
        file_path = tmp_path / "bom.txt"
        file_path.write_bytes(b"\xef\xbb\xbfhello")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        assert reader._is_text_file(file_path) is True

    def test_latin1_encoded_file(self, tmp_path: Path) -> None:
        """A Latin-1 encoded file is readable with errors='replace'."""
        file_path = tmp_path / "latin.txt"
        file_path.write_bytes(b"caf\xe9")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        assert reader._is_text_file(file_path) is True

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """A nonexistent file should not be considered text."""
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        assert reader._is_text_file(tmp_path / "nope.txt") is False


class TestHashFile:
    """Tests for FileReader._hash_file."""

    def test_hash_matches_sha256(self, tmp_path: Path) -> None:
        """_hash_file should return the same digest as standard sha256."""
        file_path = tmp_path / "data.txt"
        content = b"The quick brown fox jumps over the lazy dog."
        file_path.write_bytes(content)
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        expected = hashlib.sha256(content).hexdigest()
        assert reader._hash_file(file_path) == expected

    def test_hash_empty_file(self, tmp_path: Path) -> None:
        """Hash of an empty file should match sha256 of empty bytes."""
        file_path = tmp_path / "empty.txt"
        file_path.write_bytes(b"")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        expected = hashlib.sha256(b"").hexdigest()
        assert reader._hash_file(file_path) == expected

    def test_hash_large_file(self, tmp_path: Path) -> None:
        """_hash_file should correctly hash files larger than the chunk size."""
        file_path = tmp_path / "large.bin"
        content = b"x" * (8192 * 3 + 123)
        file_path.write_bytes(content)
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        expected = hashlib.sha256(content).hexdigest()
        assert reader._hash_file(file_path) == expected


class TestScan:
    """Tests for FileReader._scan."""

    def test_scan_single_text_file(self, tmp_path: Path) -> None:
        """Scanning a path list containing a single file."""
        file_path = tmp_path / "a.txt"
        file_path.write_text("alpha")
        reader = FileReader([file_path], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert mapping == {"a.txt": hashlib.sha256(b"alpha").hexdigest()}

    def test_scan_directory(self, tmp_path: Path) -> None:
        """Scanning a directory discovers nested text files."""
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("beta")
        (tmp_path / "c.txt").write_text("gamma")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert "c.txt" in mapping
        assert "sub/b.txt" in mapping
        assert len(mapping) == 2

    def test_scan_skips_binary_files(self, tmp_path: Path) -> None:
        """Binary files should be omitted from the mapping."""
        (tmp_path / "text.txt").write_text("hello")
        (tmp_path / "binary.bin").write_bytes(b"\x00\x01")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert "text.txt" in mapping
        assert "binary.bin" not in mapping

    def test_scan_nonexistent_path(self, tmp_path: Path) -> None:
        """A nonexistent path should yield an empty mapping."""
        reader = FileReader([tmp_path / "ghost"], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert mapping == {}

    def test_scan_multiple_paths(self, tmp_path: Path) -> None:
        """Multiple independent paths should all be scanned."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "1.txt").write_text("one")
        (dir_b / "2.txt").write_text("two")
        reader = FileReader([dir_a, dir_b], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert "1.txt" in mapping
        assert "2.txt" in mapping
        assert len(mapping) == 2

    def test_scan_nested_directories(self, tmp_path: Path) -> None:
        """Deep nesting should produce correct relative paths."""
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_text("deep")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert "a/b/c/deep.txt" in mapping

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """An empty directory should produce an empty mapping."""
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        assert mapping == {}

    def test_scan_backslash_replacement(self, tmp_path: Path) -> None:
        """Windows backslashes must be replaced with forward slashes."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("data")
        reader = FileReader([tmp_path], tmp_path / ".." / "out.json")
        mapping = reader._scan()
        for key in mapping:
            assert "\\" not in key, f"Found backslash in key: {key}"


class TestBuildAndWrite:
    """Tests for FileReader._build and _write."""

    def test_output_file_created(self, tmp_path: Path) -> None:
        """The JSON output file should be created during initialisation."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "output" / "mapping.json"
        (src / "x.txt").write_text("x")
        FileReader([src], out)
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        """The written output must be valid JSON."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "y.txt").write_text("y")
        FileReader([src], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_output_has_trailing_newline(self, tmp_path: Path) -> None:
        """The JSON file should end with a newline."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "z.txt").write_text("z")
        FileReader([src], out)
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_output_indentation(self, tmp_path: Path) -> None:
        """The JSON should be indented with two spaces."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "a.txt").write_text("a")
        (src / "b.txt").write_text("b")
        FileReader([src], out)
        text = out.read_text(encoding="utf-8")
        assert "  " in text

    def test_internal_mapping_matches_output(self, tmp_path: Path) -> None:
        """The internal _mapping should match the persisted JSON content."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "m.txt").write_text("m")
        reader = FileReader([src], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert reader._mapping == data


class TestUpdate:
    """Tests for FileReader.update."""

    def test_update_detects_new_file(self, tmp_path: Path) -> None:
        """Adding a new file and calling update should change the mapping."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "old.txt").write_text("old")
        reader = FileReader([src], out)
        old_mapping = reader._mapping.copy()
        (src / "new.txt").write_text("new")
        reader.update()
        assert reader._mapping != old_mapping
        assert "new.txt" in reader._mapping

    def test_update_detects_deleted_file(self, tmp_path: Path) -> None:
        """Deleting a file and calling update should remove it."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        target = src / "gone.txt"
        target.write_text("gone")
        reader = FileReader([src], out)
        assert "gone.txt" in reader._mapping
        target.unlink()
        reader.update()
        assert "gone.txt" not in reader._mapping

    def test_update_detects_modified_file(self, tmp_path: Path) -> None:
        """Modifying a file should update its hash."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        target = src / "mut.txt"
        target.write_text("before")
        reader = FileReader([src], out)
        old_hash = reader._mapping["mut.txt"]
        target.write_text("after")
        reader.update()
        assert reader._mapping["mut.txt"] != old_hash

    def test_update_no_change_is_noop(self, tmp_path: Path) -> None:
        """Calling update when nothing changed should keep the same mapping."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "stale.txt").write_text("stale")
        reader = FileReader([src], out)
        mtime_before = out.stat().st_mtime
        reader.update()
        mtime_after = out.stat().st_mtime
        # Because _write is only called when mapping changes, the mtime should not change.
        assert mtime_before == mtime_after

    def test_update_rewrites_json(self, tmp_path: Path) -> None:
        """When a change occurs, the JSON file should be rewritten."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "x.txt").write_text("x")
        reader = FileReader([src], out)
        (src / "y.txt").write_text("y")
        reader.update()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "y.txt" in data


class TestInit:
    """Tests for FileReader.__init__ behaviour."""

    def test_paths_are_resolved(self, tmp_path: Path) -> None:
        """Paths should be stored as absolute, resolved Path objects."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "f.txt").write_text("f")
        out = tmp_path / "out.json"
        reader = FileReader([sub], out)
        assert all(p.is_absolute() for p in reader.paths)

    def test_output_path_is_resolved(self, tmp_path: Path) -> None:
        """The output path should be stored as an absolute, resolved Path."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "f.txt").write_text("f")
        reader = FileReader([src], out)
        assert reader.output_path.is_absolute()

    def test_init_calls_build(self, tmp_path: Path) -> None:
        """Initialisation should immediately build and write the mapping."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out.json"
        (src / "f.txt").write_text("f")
        reader = FileReader([src], out)
        assert out.exists()
        assert reader._mapping

    def test_init_with_single_file_path(self, tmp_path: Path) -> None:
        """Passing a single file (not directory) as the path should work."""
        file_path = tmp_path / "single.txt"
        file_path.write_text("solo")
        out = tmp_path / "out.json"
        reader = FileReader([file_path], out)
        assert "single.txt" in reader._mapping
        assert len(reader._mapping) == 1

    def test_init_with_mixed_paths(self, tmp_path: Path) -> None:
        """A mix of files and directories should be handled."""
        dir_path = tmp_path / "dir"
        dir_path.mkdir()
        file_path = tmp_path / "file.txt"
        file_path.write_text("file")
        (dir_path / "inner.txt").write_text("inner")
        out = tmp_path / "out.json"
        reader = FileReader([file_path, dir_path], out)
        assert "file.txt" in reader._mapping
        assert "inner.txt" in reader._mapping

    def test_init_with_empty_paths(self, tmp_path: Path) -> None:
        """An empty paths list should produce an empty mapping."""
        out = tmp_path / "out.json"
        reader = FileReader([], out)
        assert reader._mapping == {}
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data == {}
