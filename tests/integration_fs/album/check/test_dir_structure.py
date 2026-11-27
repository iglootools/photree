from pathlib import Path

from photree.album.check.dir_structure import AlbumDirCheck, check_album_dir_structure
from photree.album.store.media_source import (
    MAIN_MEDIA_SOURCE,
    ios_media_source,
    std_media_source,
)

_MAIN = MAIN_MEDIA_SOURCE


def _make_dirs(album: Path, *dirs: str) -> None:
    for d in dirs:
        (album / d).mkdir(parents=True)


class TestCheckAlbumDirStructure:
    def test_no_media_source_reports_every_main_dir_missing(
        self,
        tmp_path: Path,
    ) -> None:
        check = check_album_dir_structure(tmp_path, media_sources=[])

        assert check == AlbumDirCheck(present=(), missing=_MAIN.required_subdirs)
        assert not check.success

    def test_complete_image_group_passes_with_video_group_optional(
        self,
        tmp_path: Path,
    ) -> None:
        _make_dirs(tmp_path, *_MAIN.image_subdirs)

        check = check_album_dir_structure(tmp_path, media_sources=[_MAIN])

        assert check.success
        assert check.present == _MAIN.image_subdirs
        assert check.optional_absent == (
            *_MAIN.optional_subdirs,
            *_MAIN.video_subdirs,
        )

    def test_partly_present_image_group_reports_its_missing_dirs(
        self,
        tmp_path: Path,
    ) -> None:
        _make_dirs(tmp_path, _MAIN.orig_img_dir, _MAIN.img_dir)

        check = check_album_dir_structure(tmp_path, media_sources=[_MAIN])

        assert not check.success
        assert check.present == (_MAIN.orig_img_dir, _MAIN.img_dir)
        assert check.missing == (_MAIN.jpg_dir,)

    def test_video_only_source_does_not_require_image_dirs(
        self,
        tmp_path: Path,
    ) -> None:
        ms = std_media_source("main")
        _make_dirs(tmp_path, *ms.video_subdirs)

        check = check_album_dir_structure(tmp_path, media_sources=[ms])

        assert check.success
        assert check.present == ms.video_subdirs
        assert set(ms.image_subdirs) <= set(check.optional_absent)

    def test_source_with_no_dir_requires_every_group(self, tmp_path: Path) -> None:
        check = check_album_dir_structure(tmp_path, media_sources=[_MAIN])

        assert check.missing == _MAIN.required_subdirs

    def test_edit_dirs_are_optional_and_reported_when_present(
        self,
        tmp_path: Path,
    ) -> None:
        _make_dirs(tmp_path, *_MAIN.image_subdirs, _MAIN.edit_img_dir)

        check = check_album_dir_structure(tmp_path, media_sources=[_MAIN])

        assert check.success
        assert check.optional_present == (_MAIN.edit_img_dir,)
        assert _MAIN.edit_vid_dir in check.optional_absent

    def test_each_media_source_is_checked_on_its_own(self, tmp_path: Path) -> None:
        bruno = ios_media_source("bruno")
        _make_dirs(tmp_path, *_MAIN.image_subdirs, bruno.orig_img_dir)

        check = check_album_dir_structure(tmp_path, media_sources=[_MAIN, bruno])

        assert not check.success
        assert check.missing == (bruno.img_dir, bruno.jpg_dir)
