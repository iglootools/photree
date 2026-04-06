"""Tests for photree.album.importer.selection module."""

from __future__ import annotations

from pathlib import Path

from photree.album.importer.selection import (
    has_selection,
    read_selection,
    read_selection_csv,
)
from photree.album.store.protocol import SELECTION_CSV, SELECTION_DIR


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# read_selection_csv
# ---------------------------------------------------------------------------


class TestReadSelectionCsv:
    def test_basic(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "to-import.csv"
        csv_path.write_text("IMG_0410.HEIC\nIMG_0411.HEIC\nIMG_0115.MOV\n")
        result = read_selection_csv(csv_path)
        assert result == ["IMG_0115.MOV", "IMG_0410.HEIC", "IMG_0411.HEIC"]

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "to-import.csv"
        csv_path.write_text("IMG_0410.HEIC\n\n\nIMG_0411.HEIC\n")
        result = read_selection_csv(csv_path)
        assert result == ["IMG_0410.HEIC", "IMG_0411.HEIC"]

    def test_whitespace_stripped(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "to-import.csv"
        csv_path.write_text("  IMG_0410.HEIC  \n IMG_0411.HEIC\n")
        result = read_selection_csv(csv_path)
        assert result == ["IMG_0410.HEIC", "IMG_0411.HEIC"]

    def test_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "to-import.csv"
        assert read_selection_csv(csv_path) == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "to-import.csv"
        csv_path.write_text("")
        assert read_selection_csv(csv_path) == []


# ---------------------------------------------------------------------------
# read_selection
# ---------------------------------------------------------------------------


class TestReadSelection:
    def test_dir_only(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SELECTION_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        sources = read_selection(tmp_path)
        assert sources.dir_files == ("IMG_0410.HEIC",)
        assert sources.csv_files == ()
        assert "IMG_0410.HEIC" in sources.merged

    def test_csv_only(self, tmp_path: Path) -> None:
        (tmp_path / SELECTION_CSV).write_text("IMG_0410.HEIC\n")
        sources = read_selection(tmp_path)
        assert sources.dir_files == ()
        assert sources.csv_files == ("IMG_0410.HEIC",)
        assert "IMG_0410.HEIC" in sources.merged

    def test_both_merged(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SELECTION_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        (tmp_path / SELECTION_CSV).write_text("IMG_0411.HEIC\n")
        sources = read_selection(tmp_path)
        assert sources.dir_files == ("IMG_0410.HEIC",)
        assert sources.csv_files == ("IMG_0411.HEIC",)
        assert set(sources.merged) == {"IMG_0410.HEIC", "IMG_0411.HEIC"}

    def test_dedup_by_number_prefers_dir(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SELECTION_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.JPEG").write_text("data")
        (tmp_path / SELECTION_CSV).write_text("IMG_0410.HEIC\n")
        sources = read_selection(tmp_path)
        # Dir entry preferred: JPEG from dir, not HEIC from CSV
        assert sources.merged == ("IMG_0410.JPEG",)

    def test_neither_returns_empty(self, tmp_path: Path) -> None:
        sources = read_selection(tmp_path)
        assert sources.dir_files == ()
        assert sources.csv_files == ()
        assert sources.merged == ()


# ---------------------------------------------------------------------------
# has_selection
# ---------------------------------------------------------------------------


class TestHasSelection:
    def test_dir_only(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SELECTION_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        assert has_selection(tmp_path) is True

    def test_csv_only(self, tmp_path: Path) -> None:
        (tmp_path / SELECTION_CSV).write_text("IMG_0410.HEIC\n")
        assert has_selection(tmp_path) is True

    def test_both(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SELECTION_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        (tmp_path / SELECTION_CSV).write_text("IMG_0411.HEIC\n")
        assert has_selection(tmp_path) is True

    def test_neither(self, tmp_path: Path) -> None:
        assert has_selection(tmp_path) is False

    def test_empty_dir_no_csv(self, tmp_path: Path) -> None:
        (tmp_path / SELECTION_DIR).mkdir()
        assert has_selection(tmp_path) is False

    def test_empty_csv_no_dir(self, tmp_path: Path) -> None:
        (tmp_path / SELECTION_CSV).write_text("")
        assert has_selection(tmp_path) is False
