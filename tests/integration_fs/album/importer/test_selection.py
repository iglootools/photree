"""Tests for photree.album.importer.selection module."""

from __future__ import annotations

from pathlib import Path

from photree.album.importer.selection import (
    has_selection,
    read_selection,
    read_selection_csv,
)
from photree.album.store.protocol import ios_import_csv, ios_import_dir

SEL_DIR = ios_import_dir("main")  # to-import-ios-main
SEL_CSV = ios_import_csv("main")  # to-import-ios-main.csv


# ---------------------------------------------------------------------------
# read_selection_csv
# ---------------------------------------------------------------------------


class TestReadSelectionCsv:
    def test_basic(self, tmp_path: Path) -> None:
        csv_path = tmp_path / SEL_CSV
        csv_path.write_text("IMG_0410.HEIC\nIMG_0411.HEIC\nIMG_0115.MOV\n")
        result = read_selection_csv(csv_path)
        assert result == ["IMG_0115.MOV", "IMG_0410.HEIC", "IMG_0411.HEIC"]

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        csv_path = tmp_path / SEL_CSV
        csv_path.write_text("IMG_0410.HEIC\n\n\nIMG_0411.HEIC\n")
        result = read_selection_csv(csv_path)
        assert result == ["IMG_0410.HEIC", "IMG_0411.HEIC"]

    def test_whitespace_stripped(self, tmp_path: Path) -> None:
        csv_path = tmp_path / SEL_CSV
        csv_path.write_text("  IMG_0410.HEIC  \n IMG_0411.HEIC\n")
        result = read_selection_csv(csv_path)
        assert result == ["IMG_0410.HEIC", "IMG_0411.HEIC"]

    def test_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        csv_path = tmp_path / SEL_CSV
        assert read_selection_csv(csv_path) == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        csv_path = tmp_path / SEL_CSV
        csv_path.write_text("")
        assert read_selection_csv(csv_path) == []


# ---------------------------------------------------------------------------
# read_selection
# ---------------------------------------------------------------------------


class TestReadSelection:
    def test_dir_only(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SEL_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        sources = read_selection(sel_dir, tmp_path / SEL_CSV)
        assert sources.dir_files == ("IMG_0410.HEIC",)
        assert sources.csv_files == ()
        assert "IMG_0410.HEIC" in sources.merged

    def test_csv_only(self, tmp_path: Path) -> None:
        (tmp_path / SEL_CSV).write_text("IMG_0410.HEIC\n")
        sources = read_selection(tmp_path / SEL_DIR, tmp_path / SEL_CSV)
        assert sources.dir_files == ()
        assert sources.csv_files == ("IMG_0410.HEIC",)
        assert "IMG_0410.HEIC" in sources.merged

    def test_both_merged(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SEL_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        (tmp_path / SEL_CSV).write_text("IMG_0411.HEIC\n")
        sources = read_selection(sel_dir, tmp_path / SEL_CSV)
        assert sources.dir_files == ("IMG_0410.HEIC",)
        assert sources.csv_files == ("IMG_0411.HEIC",)
        assert set(sources.merged) == {"IMG_0410.HEIC", "IMG_0411.HEIC"}

    def test_dedup_by_number_prefers_dir(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SEL_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.JPEG").write_text("data")
        (tmp_path / SEL_CSV).write_text("IMG_0410.HEIC\n")
        sources = read_selection(sel_dir, tmp_path / SEL_CSV)
        # Dir entry preferred: JPEG from dir, not HEIC from CSV
        assert sources.merged == ("IMG_0410.JPEG",)

    def test_none_sources_returns_empty(self, tmp_path: Path) -> None:
        sources = read_selection(None, None)
        assert sources.dir_files == ()
        assert sources.csv_files == ()
        assert sources.merged == ()

    def test_missing_paths_return_empty(self, tmp_path: Path) -> None:
        sources = read_selection(tmp_path / SEL_DIR, tmp_path / SEL_CSV)
        assert sources.merged == ()


# ---------------------------------------------------------------------------
# has_selection
# ---------------------------------------------------------------------------


class TestHasSelection:
    def test_dir_only(self, tmp_path: Path) -> None:
        sel_dir = tmp_path / SEL_DIR
        sel_dir.mkdir()
        (sel_dir / "IMG_0410.HEIC").write_text("data")
        assert has_selection(sel_dir, tmp_path / SEL_CSV) is True

    def test_csv_only(self, tmp_path: Path) -> None:
        (tmp_path / SEL_CSV).write_text("IMG_0410.HEIC\n")
        assert has_selection(tmp_path / SEL_DIR, tmp_path / SEL_CSV) is True

    def test_neither(self, tmp_path: Path) -> None:
        assert has_selection(tmp_path / SEL_DIR, tmp_path / SEL_CSV) is False

    def test_none_sources(self, tmp_path: Path) -> None:
        assert has_selection(None, None) is False

    def test_empty_dir_no_csv(self, tmp_path: Path) -> None:
        (tmp_path / SEL_DIR).mkdir()
        assert has_selection(tmp_path / SEL_DIR, tmp_path / SEL_CSV) is False
