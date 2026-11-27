from pathlib import Path

import pytest

from photree.album.importer.album_import import (
    TaskIssue,
    run_import,
    validate_album_import,
)
from photree.album.importer.collision import (
    ArchiveCollision,
    MediaSourceClash,
    MediaSourceClashError,
    MediaSourceClashErrorKind,
)
from photree.album.staging import ios_import_dir, std_import_dir
from photree.album.store.media_source import ios_media_source, std_media_source
from photree.album.store.metadata import load_album_metadata
from photree.foundation.layout import PHOTREE_DIR
from tests.fakes import noop_convert
from tests.testkit import write_file


def _stage_std(album: Path, name: str, filename: str = "photo.jpg") -> Path:
    staged = album / std_import_dir(name) / "orig" / filename
    write_file(staged)
    return staged


def _run_std_import(tmp_path: Path, album: Path, *, dry_run: bool = False) -> None:
    run_import(
        album_dir=album,
        image_capture_dir=tmp_path / "no-image-capture",
        convert_file=noop_convert,
        dry_run=dry_run,
    )


def _stage_ios(album: Path, name: str) -> None:
    write_file(album / ios_import_dir(name) / "IMG_0001.HEIC")


def _image_capture_dir(tmp_path: Path) -> Path:
    ic_dir = tmp_path / "ic"
    write_file(ic_dir / "IMG_0001.HEIC")
    write_file(ic_dir / "IMG_0001.AAE")
    return ic_dir


class TestValidateAlbumImport:
    def test_ios_number_already_archived_is_a_collision(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = ios_media_source("main")
        write_file(album / ms.orig_img_dir / "IMG_0001.HEIC")
        _stage_ios(album, "main")

        validation = validate_album_import(album, ["IMG_0001.HEIC", "IMG_0001.AAE"])

        assert validation.errors == (TaskIssue(ms, ArchiveCollision(ms, ("0001",))),)


class TestRunImportAlbumMetadata:
    def test_second_import_keeps_the_album_id(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _stage_std(album, "nelu", "a.jpg")
        _run_std_import(tmp_path, album)
        first = load_album_metadata(album)

        _stage_std(album, "nelu", "b.jpg")
        _run_std_import(tmp_path, album)

        assert first is not None
        assert load_album_metadata(album) == first

    def test_dry_run_writes_no_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _stage_std(album, "nelu")

        _run_std_import(tmp_path, album, dry_run=True)

        assert not (album / PHOTREE_DIR).exists()


class TestMediaSourceClash:
    def test_std_task_clashes_with_existing_ios_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        write_file(album / ios_media_source("main").orig_img_dir / "IMG_0001.HEIC")
        _stage_std(album, "main")

        validation = validate_album_import(album, [])

        ms = std_media_source("main")
        assert validation.errors == (
            TaskIssue(
                ms,
                MediaSourceClash(ms, MediaSourceClashErrorKind.EXISTING_ARCHIVE),
            ),
        )

    def test_ios_and_std_staged_under_one_name_clash(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _stage_ios(album, "main")
        _stage_std(album, "main")

        validation = validate_album_import(album, ["IMG_0001.HEIC", "IMG_0001.AAE"])

        assert [i.detail for i in validation.errors] == [
            MediaSourceClash(
                ios_media_source("main"),
                MediaSourceClashErrorKind.STAGED,
            ),
            MediaSourceClash(
                std_media_source("main"),
                MediaSourceClashErrorKind.STAGED,
            ),
        ]

    def test_distinct_names_do_not_clash(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        write_file(album / ios_media_source("main").orig_img_dir / "IMG_0001.HEIC")
        _stage_std(album, "nelu")

        assert validate_album_import(album, []).errors == ()

    def test_run_import_refuses_before_any_mutation(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        write_file(album / ios_media_source("main").orig_img_dir / "IMG_0001.HEIC")
        staged = _stage_std(album, "main")

        with pytest.raises(MediaSourceClashError) as exc_info:
            run_import(
                album_dir=album,
                image_capture_dir=_image_capture_dir(tmp_path),
                convert_file=noop_convert,
            )

        assert exc_info.value.clash.media_source == std_media_source("main")
        assert staged.is_file()
        assert not (album / std_media_source("main").archive_dir).exists()
