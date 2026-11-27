from functools import partial
from pathlib import Path

import pytest

from photree.album.browsable import (
    is_incomplete,
    mark_incomplete,
    refresh_browsable_dir,
)
from photree.album.fix import (
    MissingArchiveError,
    RmUpstreamIncompleteSignalError,
    RmUpstreamRefusedError,
    SignalSkipReason,
    rm_upstream,
    run_fix,
)
from photree.album.fix.output import format_fix_result
from photree.album.fix.rm_upstream import MediaKind
from photree.album.formats import IMG_EXTENSIONS
from photree.album.jpeg import refresh_jpeg_dir
from photree.album.refresh import refresh_album_derived_data
from photree.album.store.media_source import MAIN_MEDIA_SOURCE, std_media_source
from photree.common.fs import list_files
from photree.foundation.linking import LinkMode
from tests.fakes import FakeExifTool, copy_convert_single
from tests.testkit import file_names, write_files

MC = MAIN_MEDIA_SOURCE


STD = std_media_source("nelu")


def _ios_album_without_jpg(album: Path) -> None:
    write_files(album / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
    write_files(album / "main-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])


_THREE_HEICS = ["IMG_0001.HEIC", "IMG_0002.HEIC", "IMG_0003.HEIC"]


def _convert_only_the_first(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Stand in for sips failing on every image but IMG_0001."""
    if src.stem != "IMG_0001":
        message = f"sips failed on {src.name}"
        raise OSError(message)
    return copy_convert_single(src, dst_dir, dry_run=dry_run)


class _InterruptedError(Exception):
    """Stands in for a Ctrl-C partway through a rebuild."""


def _interrupt_after_first_file(_filename: str, *, success: bool) -> None:  # noqa: ARG001 - FileEnd's signature
    raise _InterruptedError


class TestRmUpstreamHeic:
    def test_removes_upstream_when_jpeg_deleted(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0410.HEIC", "IMG_0410.AAE"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0410.HEIC", "IMG_O0410.AAE"])
        write_files(tmp_path / "main-img", ["IMG_E0410.HEIC"])
        # main-jpg is empty — the jpeg was "deleted" by the user
        write_files(tmp_path / "main-jpg", [])

        # The only image deleted everywhere: needs --force (would empty the archive)
        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=True)

        assert result.heic.removed_browsable == ("IMG_E0410.HEIC",)
        assert set(result.heic.removed_rendered) == {"IMG_E0410.HEIC", "IMG_O0410.AAE"}
        assert set(result.heic.removed_orig) == {"IMG_0410.HEIC", "IMG_0410.AAE"}
        assert file_names(tmp_path / "main-img") == set()
        assert file_names(tmp_path / "ios-main/edit-img") == set()
        assert file_names(tmp_path / "ios-main/orig-img") == set()

    def test_keeps_files_with_jpeg_present(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC"],
        )
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        # Only IMG_0001.jpg present — IMG_0002 was deleted
        write_files(tmp_path / "main-jpg", ["IMG_0001.jpg"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_browsable == ("IMG_0002.HEIC",)
        assert "IMG_0002.HEIC" not in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.AAE" in file_names(tmp_path / "ios-main/orig-img")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        """No deletions when all jpegs are present."""
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-jpg", ["IMG_0001.jpg"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_browsable == ()
        assert result.heic.removed_rendered == ()
        assert result.heic.removed_orig == ()

    def test_handles_jpg_copy_as_is(self, tmp_path: Path) -> None:
        """JPG files in main-img are copied as-is to main-jpg."""
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.JPG"])
        write_files(tmp_path / "main-img", ["IMG_0001.JPG"])
        # JPG was deleted from main-jpg
        write_files(tmp_path / "main-jpg", [])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=True)

        assert result.heic.removed_browsable == ("IMG_0001.JPG",)

    def test_removes_upstream_when_browsable_img_deleted(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC", "IMG_0002.AAE"],
        )
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_O0001.AAE"])
        # User deleted IMG_E0001.HEIC from main-img
        write_files(tmp_path / "main-img", ["IMG_0002.HEIC"])
        write_files(tmp_path / "main-jpg", ["IMG_E0001.jpg", "IMG_0002.jpg"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_jpeg == ("IMG_E0001.jpg",)
        # Already deleted by the user.
        assert result.heic.removed_browsable == ()
        assert set(result.heic.removed_rendered) == {"IMG_E0001.HEIC", "IMG_O0001.AAE"}
        assert set(result.heic.removed_orig) == {"IMG_0001.HEIC", "IMG_0001.AAE"}
        assert "IMG_0002.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0002.HEIC" in file_names(tmp_path / "main-img")
        assert "IMG_0002.jpg" in file_names(tmp_path / "main-jpg")

    def test_both_jpeg_and_heic_deletions_merged(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0002.HEIC", "IMG_0003.HEIC"],
        )
        # IMG_0002 deleted from main-img, IMG_0003 jpeg deleted from main-jpg
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0003.HEIC"])
        write_files(tmp_path / "main-jpg", ["IMG_0001.jpg"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        removed_numbers = {
            "".join(c for c in f if c.isdigit()) for f in result.heic.removed_orig
        }
        assert "0002" in removed_numbers
        assert "0003" in removed_numbers
        assert "0001" not in removed_numbers

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-jpg", [])

        [result] = rm_upstream(tmp_path, [MC], dry_run=True, force=True)

        assert result.heic.removed_browsable == ("IMG_0001.HEIC",)
        assert "IMG_0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in file_names(tmp_path / "main-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when directories don't exist."""
        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_browsable == ()
        assert result.mov.removed_orig == ()


class TestRmUpstreamMov:
    def test_removes_upstream_when_browsable_vid_deleted(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_0115.MOV"])
        write_files(tmp_path / "ios-main/edit-vid", ["IMG_E0115.MOV"])
        write_files(tmp_path / "main-vid", [])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=True)

        assert result.mov.removed_rendered == ("IMG_E0115.MOV",)
        assert result.mov.removed_orig == ("IMG_0115.MOV",)
        assert file_names(tmp_path / "ios-main/edit-vid") == set()
        assert file_names(tmp_path / "ios-main/orig-vid") == set()

    def test_keeps_files_with_browsable_vid_present(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_0001.MOV", "IMG_0002.MOV"])
        write_files(tmp_path / "ios-main/edit-vid", ["IMG_E0001.MOV"])
        write_files(tmp_path / "main-vid", ["IMG_E0001.MOV"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        # IMG_0002 was removed from main-vid → propagate
        assert result.mov.removed_orig == ("IMG_0002.MOV",)
        assert "IMG_0001.MOV" in file_names(tmp_path / "ios-main/orig-vid")
        assert "IMG_E0001.MOV" in file_names(tmp_path / "ios-main/edit-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_0001.MOV"])
        write_files(tmp_path / "main-vid", ["IMG_0001.MOV"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.mov.removed_rendered == ()
        assert result.mov.removed_orig == ()


class TestRmUpstreamSignals:
    def test_missing_jpg_dir_deletes_nothing(self, tmp_path: Path) -> None:
        """--skip-heic-to-jpeg leaves no main-jpg: that is not a deletion."""
        _ios_album_without_jpg(tmp_path)

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_orig == ()
        assert file_names(tmp_path / "ios-main/orig-img") == {
            "IMG_0001.HEIC",
            "IMG_0002.HEIC",
        }
        assert [(s.directory, s.reason) for s in result.skipped] == [
            ("main-jpg", SignalSkipReason.MISSING),
            ("main-vid", SignalSkipReason.MISSING),
        ]

    def test_empty_jpg_dir_deletes_nothing(self, tmp_path: Path) -> None:
        _ios_album_without_jpg(tmp_path)
        write_files(tmp_path / "main-jpg", [])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_orig == ()
        assert len(file_names(tmp_path / "ios-main/orig-img")) == 2
        assert ("main-jpg", SignalSkipReason.NO_EXPECTED_FILES) in [
            (s.directory, s.reason) for s in result.skipped
        ]

    def test_missing_vid_dir_deletes_no_video(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        write_files(tmp_path / "std-nelu/edit-vid", ["clip.mov"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.mov.removed_orig == ()
        assert file_names(tmp_path / "std-nelu/orig-vid") == {
            "clip.mov",
            "other.mov",
        }
        assert ("nelu-vid", SignalSkipReason.MISSING) in [
            (s.directory, s.reason) for s in result.skipped
        ]

    def test_img_dir_older_than_the_archive_deletes_nothing(
        self,
        tmp_path: Path,
    ) -> None:
        """main-img was built before the edit reached edit-img: nothing was deleted."""
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        write_files(tmp_path / "main-jpg", ["IMG_0001.jpg", "IMG_0002.jpg"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_orig == ()
        assert result.heic.removed_rendered == ()
        assert file_names(tmp_path / "ios-main/edit-img") == {"IMG_E0001.HEIC"}

    def test_jpg_dir_older_than_the_img_dir_deletes_nothing(
        self,
        tmp_path: Path,
    ) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_E0001.HEIC", "IMG_0002.HEIC"])
        write_files(tmp_path / "main-jpg", ["IMG_0001.jpg", "IMG_0002.jpg"])

        [result] = rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert result.heic.removed_orig == ()
        assert result.heic.removed_rendered == ()

    def test_skip_is_reported_in_fix_output(self, tmp_path: Path) -> None:
        _ios_album_without_jpg(tmp_path)

        lines = format_fix_result(
            run_fix(
                tmp_path,
                dry_run=False,
                rm_upstream_flag=True,
            ),
        )

        assert any("main-jpg" in line and "missing" in line for line in lines)


class TestRmUpstreamAllKeysRefusal:
    def test_emptied_vid_dir_is_refused(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        write_files(tmp_path / "nelu-vid", [])

        with pytest.raises(RmUpstreamRefusedError) as exc_info:
            rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert exc_info.value.media_source == "nelu"
        assert exc_info.value.kind == MediaKind.VIDEOS
        assert exc_info.value.key_count == 2
        assert file_names(tmp_path / "std-nelu/orig-vid") == {
            "clip.mov",
            "other.mov",
        }

    def test_emptied_img_dir_is_refused(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        write_files(tmp_path / "main-img", [])
        write_files(tmp_path / "main-jpg", ["IMG_0001.jpg", "IMG_0002.jpg"])

        with pytest.raises(RmUpstreamRefusedError) as exc_info:
            rm_upstream(tmp_path, [MC], dry_run=False, force=False)

        assert exc_info.value.kind == MediaKind.IMAGES
        assert len(file_names(tmp_path / "ios-main/orig-img")) == 2
        assert len(file_names(tmp_path / "main-jpg")) == 2

    def test_force_overrides_refusal(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        write_files(tmp_path / "nelu-vid", [])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=True)

        assert result.mov.removed_orig == ("clip.mov",)

    def test_run_fix_refusal_leaves_other_sources_untouched(
        self,
        tmp_path: Path,
    ) -> None:
        """All sources are planned first: one refusal means no deletion at all."""
        # "main" has a legitimate deletion, "nelu" would be emptied.
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        write_files(tmp_path / "nelu-vid", [])

        with pytest.raises(RmUpstreamRefusedError):
            run_fix(
                tmp_path,
                dry_run=False,
                rm_upstream_flag=True,
            )

        assert "IMG_0002.HEIC" in file_names(tmp_path / "ios-main/orig-img")


class TestRmUpstreamIncompleteSignal:
    def test_failed_jpeg_conversions_are_not_deleted(self, tmp_path: Path) -> None:
        """Sips failed on 2 of 3 JPEGs: their originals must survive rm-upstream."""
        write_files(tmp_path / "ios-main/orig-img", _THREE_HEICS)
        write_files(tmp_path / "main-img", _THREE_HEICS)
        refresh_jpeg_dir(
            tmp_path / "main-img",
            tmp_path / "main-jpg",
            convert_file=_convert_only_the_first,
        )
        assert list_files(tmp_path / "main-jpg") == ["IMG_0001.jpg"]

        with pytest.raises(RmUpstreamIncompleteSignalError) as exc_info:
            run_fix(tmp_path, dry_run=False, rm_upstream_flag=True)

        assert exc_info.value.media_source == "main"
        assert exc_info.value.directories == ("main-jpg",)
        assert "photree album refresh" in str(exc_info.value)
        assert file_names(tmp_path / "ios-main/orig-img") == set(_THREE_HEICS)
        assert file_names(tmp_path / "main-img") == set(_THREE_HEICS)

    def test_force_does_not_override_an_incomplete_signal(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", _THREE_HEICS)
        write_files(tmp_path / "main-img", _THREE_HEICS)
        refresh_jpeg_dir(
            tmp_path / "main-img",
            tmp_path / "main-jpg",
            convert_file=_convert_only_the_first,
        )

        with pytest.raises(RmUpstreamIncompleteSignalError):
            run_fix(tmp_path, dry_run=False, rm_upstream_flag=True, force=True)

        assert file_names(tmp_path / "ios-main/orig-img") == set(_THREE_HEICS)

    def test_interrupted_browsable_rebuild_is_not_read_as_deletions(
        self,
        tmp_path: Path,
    ) -> None:
        write_files(tmp_path / "ios-main/orig-img", _THREE_HEICS)
        with pytest.raises(_InterruptedError):
            refresh_browsable_dir(
                tmp_path / "ios-main/orig-img",
                tmp_path / "ios-main/edit-img",
                tmp_path / "main-img",
                media_extensions=IMG_EXTENSIONS,
                key_fn=MC.key_fn,
                link_mode=LinkMode.COPY,
                on_file_end=_interrupt_after_first_file,
            )
        assert list_files(tmp_path / "main-img") == ["IMG_0001.HEIC"]

        with pytest.raises(RmUpstreamIncompleteSignalError) as exc_info:
            run_fix(tmp_path, dry_run=False, rm_upstream_flag=True)

        assert exc_info.value.directories == ("main-img",)
        assert file_names(tmp_path / "ios-main/orig-img") == set(_THREE_HEICS)

    def test_deletions_propagate_once_a_refresh_completes(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", _THREE_HEICS)
        refresh = partial(
            refresh_album_derived_data,
            tmp_path,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
        )
        refresh(convert_file=_convert_only_the_first)
        refresh(convert_file=copy_convert_single)
        (tmp_path / "main-jpg/IMG_0002.jpg").unlink()

        result = run_fix(tmp_path, dry_run=False, rm_upstream_flag=True)

        assert result.rm_upstream_result is not None
        assert result.rm_upstream_result.heic_orig == 1
        assert file_names(tmp_path / "ios-main/orig-img") == {
            "IMG_0001.HEIC",
            "IMG_0003.HEIC",
        }

    def test_refresh_rebuilds_a_marked_dir_whose_files_pass_the_check(
        self,
        tmp_path: Path,
    ) -> None:
        """The marker alone makes refresh rebuild, or rm-upstream stays refused."""
        write_files(tmp_path / "ios-main/orig-img", _THREE_HEICS)
        refresh = partial(
            refresh_album_derived_data,
            tmp_path,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
            convert_file=copy_convert_single,
        )
        refresh()
        for subdir in ("main-img", "main-jpg"):
            mark_incomplete(tmp_path / subdir)

        refresh()

        assert not is_incomplete(tmp_path / "main-img")
        assert not is_incomplete(tmp_path / "main-jpg")


class TestRmUpstreamStd:
    def test_removes_upstream_when_jpeg_deleted(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        write_files(tmp_path / "nelu-img", ["sunset.jpg"])
        # nelu-jpg is empty — jpeg was "deleted" by the user
        write_files(tmp_path / "nelu-jpg", [])

        # The only image deleted everywhere: needs --force (would empty the archive)
        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=True)

        assert result.heic.removed_browsable == ("sunset.jpg",)
        assert result.heic.removed_rendered == ("sunset.jpg",)
        assert result.heic.removed_orig == ("sunset.heic",)
        assert file_names(tmp_path / "nelu-img") == set()
        assert file_names(tmp_path / "std-nelu/edit-img") == set()
        assert file_names(tmp_path / "std-nelu/orig-img") == set()

    def test_keeps_files_with_jpeg_present(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        write_files(tmp_path / "nelu-img", ["sunset.heic", "beach.png"])
        # Only sunset.jpg present — beach was deleted
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert "beach.png" in result.heic.removed_orig
        assert "sunset.heic" in file_names(tmp_path / "std-nelu/orig-img")
        assert "beach.png" not in file_names(tmp_path / "std-nelu/orig-img")

    def test_removes_upstream_when_browsable_img_deleted(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        # User deleted sunset from nelu-img
        write_files(tmp_path / "nelu-img", ["beach.png"])
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg", "beach.png"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.heic.removed_jpeg == ("sunset.jpg",)
        assert result.heic.removed_orig == ("sunset.heic",)
        assert "beach.png" in file_names(tmp_path / "std-nelu/orig-img")

    def test_video_upstream_propagation(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        write_files(tmp_path / "std-nelu/edit-vid", ["clip.mov"])
        # User deleted other.mov from nelu-vid
        write_files(tmp_path / "nelu-vid", ["clip.mov"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.mov.removed_orig == ("other.mov",)
        assert "clip.mov" in file_names(tmp_path / "std-nelu/orig-vid")
        assert "other.mov" not in file_names(tmp_path / "std-nelu/orig-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.heic.removed_browsable == ()
        assert result.heic.removed_rendered == ()
        assert result.heic.removed_orig == ()

    def test_raises_when_archive_missing(self, tmp_path: Path) -> None:
        write_files(tmp_path / "nelu-img", ["sunset.heic"])

        with pytest.raises(MissingArchiveError) as exc_info:
            rm_upstream(tmp_path, [STD], dry_run=False, force=False)
        assert exc_info.value.archive_dir == "std-nelu"

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when archive exists but no browsable dirs."""
        write_files(tmp_path / "std-nelu/orig-img", [])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.heic.removed_browsable == ()
        assert result.mov.removed_orig == ()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-jpg", [])

        [result] = rm_upstream(tmp_path, [STD], dry_run=True, force=True)

        assert result.heic.removed_browsable == ("sunset.heic",)
        assert "sunset.heic" in file_names(tmp_path / "std-nelu/orig-img")
        assert "sunset.heic" in file_names(tmp_path / "nelu-img")
