from pathlib import Path

from photree.album.check.std import (
    DuplicateStem,
    check_duplicate_stems,
    check_std_media_source_integrity,
)
from photree.album.formats import IMG_EXTENSIONS
from photree.album.store.media_source import std_media_source
from photree.foundation.linking import LinkMode
from tests.testkit import write_file, write_files


class TestCheckDuplicateStems:
    def test_stems_differing_only_in_case_are_duplicates(self, tmp_path: Path) -> None:
        directory = write_files(tmp_path / "orig", ["Photo.HEIC", "photo.jpg"])
        assert check_duplicate_stems(directory, IMG_EXTENSIONS) == (
            DuplicateStem(
                directory="orig",
                stem="photo",
                files=("Photo.HEIC", "photo.jpg"),
            ),
        )

    def test_distinct_stems_are_not_duplicates(self, tmp_path: Path) -> None:
        directory = write_files(tmp_path / "orig", ["a.heic", "b.jpg"])
        assert check_duplicate_stems(directory, IMG_EXTENSIONS) == ()


class TestStdMediaSourceIntegrity:
    def test_case_insensitive_duplicate_stems_fail(self, tmp_path: Path) -> None:
        ms = std_media_source("nelu")
        write_file(tmp_path / ms.orig_img_dir / "Photo.HEIC")
        write_file(tmp_path / ms.orig_img_dir / "photo.jpg")
        result = check_std_media_source_integrity(
            tmp_path,
            ms,
            link_mode=LinkMode.HARDLINK,
        )
        assert not result.success
        assert [d.stem for d in result.duplicate_stems] == ["photo"]
