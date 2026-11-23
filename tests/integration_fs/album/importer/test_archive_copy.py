"""Tests for photree.album.importer.archive_copy."""

from pathlib import Path

import pytest

from photree.album.importer.archive_copy import (
    IMPORT_IN_PROGRESS_DIR,
    copy_into_archive,
)
from photree.foundation.layout import PHOTREE_DIR


def _source(tmp_path: Path, name: str) -> Path:
    src = tmp_path / "staging" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(name)
    return src


def _in_progress(album: Path) -> Path:
    return album / PHOTREE_DIR / IMPORT_IN_PROGRESS_DIR


class TestCopyIntoArchive:
    def test_copies_every_file_into_its_archive_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        a, b = _source(tmp_path, "a.jpg"), _source(tmp_path, "b.mov")

        copy_into_archive(
            album,
            [(a, album / "std-x/orig-img"), (b, album / "std-x/orig-vid")],
        )

        assert (album / "std-x/orig-img/a.jpg").read_text() == "a.jpg"
        assert (album / "std-x/orig-vid/b.mov").read_text() == "b.mov"
        assert a.is_file()
        assert not _in_progress(album).exists()

    def test_failed_copy_leaves_archive_untouched(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        a = _source(tmp_path, "a.jpg")
        missing = tmp_path / "staging" / "gone.jpg"

        with pytest.raises(FileNotFoundError):
            copy_into_archive(
                album,
                [(a, album / "std-x/orig-img"), (missing, album / "std-x/orig-img")],
            )

        assert not (album / "std-x").exists()
        assert not _in_progress(album).exists()

    def test_failed_move_removes_files_already_moved(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        a, b = _source(tmp_path, "a.jpg"), _source(tmp_path, "b.mov")
        # A file where the second archive dir should be makes its move fail.
        (album / "std-x").mkdir(parents=True)
        (album / "std-x/orig-vid").write_text("not a dir")

        with pytest.raises(FileExistsError):
            copy_into_archive(
                album,
                [(a, album / "std-x/orig-img"), (b, album / "std-x/orig-vid")],
            )

        assert not (album / "std-x/orig-img/a.jpg").exists()
        assert not _in_progress(album).exists()

    def test_leftover_of_killed_run_is_discarded(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        leftover = _in_progress(album) / "std-x/orig-img/old.jpg"
        leftover.parent.mkdir(parents=True)
        leftover.write_text("half")
        a = _source(tmp_path, "a.jpg")

        copy_into_archive(album, [(a, album / "std-x/orig-img")])

        assert not (album / "std-x/orig-img/old.jpg").exists()
        assert not _in_progress(album).exists()

    def test_pair_listed_twice_is_copied_once(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        a = _source(tmp_path, "a.jpg")

        copy_into_archive(
            album,
            [(a, album / "std-x/orig-img"), (a, album / "std-x/orig-img")],
        )

        assert (album / "std-x/orig-img/a.jpg").is_file()
