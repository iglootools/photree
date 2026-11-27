"""Regression tests for destructive fix operations: refusals and skipped signals."""

from functools import partial
from pathlib import Path

import pytest

from photree.album.browsable import (
    is_incomplete,
    mark_incomplete,
    refresh_browsable_dir,
)
from photree.album.fix import (
    FixValidationError,
    FixValidationErrorKind,
    RmUpstreamIncompleteSignalError,
    RmUpstreamRefusedError,
    SignalSkipReason,
    rm_upstream,
    run_fix,
    validate_fix_flags,
)
from photree.album.fix.ios import (
    FixIosValidationError,
    FixIosValidationErrorKind,
    MiscategorizedAction,
    MiscategorizedMoveConflictError,
    prefer_higher_quality_when_dups,
    run_fix_ios,
    validate_fix_flags as validate_fix_ios_flags,
)
from photree.album.fix.ios.miscategorized import fix_miscategorized
from photree.album.fix.ios.output import format_fix_ios_result
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


# ---------------------------------------------------------------------------
# rm-upstream: missing/empty signal directories
# ---------------------------------------------------------------------------


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
        assert file_names(tmp_path / "std-nelu/orig-vid") == {"clip.mov", "other.mov"}
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


# ---------------------------------------------------------------------------
# rm-upstream: refusing to empty an archive
# ---------------------------------------------------------------------------


class TestRmUpstreamAllKeysRefusal:
    def test_emptied_vid_dir_is_refused(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        write_files(tmp_path / "nelu-vid", [])

        with pytest.raises(RmUpstreamRefusedError) as exc_info:
            rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert exc_info.value.media_source == "nelu"
        assert exc_info.value.kind == MediaKind.VIDEOS
        assert exc_info.value.key_count == 2
        assert file_names(tmp_path / "std-nelu/orig-vid") == {"clip.mov", "other.mov"}

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


# ---------------------------------------------------------------------------
# rm-upstream: refusing signal dirs a refresh left incomplete
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# run_fix / run_fix_ios reporting
# ---------------------------------------------------------------------------


class TestFixReporting:
    def test_no_orphans_found_is_reported(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])

        result = run_fix(tmp_path, dry_run=False, rm_orphan_flag=True)

        assert result.rm_orphan_removed_by_dir == ()
        assert format_fix_result(result) == ["Done. No orphans found."]

    def test_dry_run_says_what_would_be_removed(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "std-nelu/edit-img", ["sunset.jpg", "orphan.jpg"])

        result = run_fix(tmp_path, dry_run=True, rm_orphan_flag=True)

        assert format_fix_result(result, dry_run=True) == [
            "Would remove 1 orphan(s): 1 from edit-img.",
        ]
        assert (tmp_path / "std-nelu/edit-img/orphan.jpg").exists()

    def test_no_media_sources_is_reported(self, tmp_path: Path) -> None:
        result = run_fix(tmp_path, dry_run=False, rm_orphan_flag=True)

        assert result.no_media_sources
        assert format_fix_result(result) == ["No media sources found; nothing to fix."]

    def test_no_duplicates_found_is_reported(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])

        result = run_fix_ios(
            tmp_path,
            dry_run=False,
            prefer_higher_quality_when_dups=True,
        )

        assert format_fix_ios_result(result) == ["Done. No duplicates found."]

    def test_no_ios_media_sources_is_reported(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])

        result = run_fix_ios(tmp_path, dry_run=False, rm_orphan_sidecar=True)

        assert result.no_ios_media_sources
        assert format_fix_ios_result(result) == [
            "No iOS media sources found; nothing to fix.",
        ]


class TestFixFlagValidation:
    def test_no_fix_specified(self) -> None:
        with pytest.raises(FixValidationError) as exc_info:
            validate_fix_flags(rm_upstream=False, rm_orphan=False)
        assert exc_info.value.kind == FixValidationErrorKind.NO_FIX_SPECIFIED

    def test_ios_mutually_exclusive_flags(self) -> None:
        with pytest.raises(FixIosValidationError) as exc_info:
            validate_fix_ios_flags(
                rm_orphan_sidecar=False,
                prefer_higher_quality_when_dups=False,
                rm_miscategorized=True,
                rm_miscategorized_safe=False,
                mv_miscategorized=True,
            )
        assert exc_info.value.kind == FixIosValidationErrorKind.MUTUALLY_EXCLUSIVE
        assert exc_info.value.flags == ("--rm-miscategorized", "--mv-miscategorized")

    def test_ios_no_fix_specified(self) -> None:
        with pytest.raises(FixIosValidationError) as exc_info:
            validate_fix_ios_flags(
                rm_orphan_sidecar=False,
                prefer_higher_quality_when_dups=False,
                rm_miscategorized=False,
                rm_miscategorized_safe=False,
                mv_miscategorized=False,
            )
        assert exc_info.value.kind == FixIosValidationErrorKind.NO_FIX_SPECIFIED


# ---------------------------------------------------------------------------
# iOS fixes
# ---------------------------------------------------------------------------


class TestPreferHigherQualityRanking:
    def test_keeps_only_dng_when_dng_and_heic(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0235.DNG", "IMG_0235.HEIC", "IMG_0235.JPG"],
        )

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert file_names(tmp_path / "ios-main/orig-img") == {"IMG_0235.DNG"}
        assert result.removed_by_dir == (
            ("orig-img", ("IMG_0235.HEIC", "IMG_0235.JPG")),
        )

    def test_keeps_heic_over_heif(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.HEIF"])

        prefer_higher_quality_when_dups(tmp_path, MC)

        assert file_names(tmp_path / "ios-main/orig-img") == {"IMG_0001.HEIC"}


class TestMvMiscategorizedOverwrite:
    def test_refuses_to_overwrite_existing_target(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").write_text("keep-me")

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            fix_miscategorized(
                tmp_path,
                [MC],
                action=MiscategorizedAction.MV,
                dry_run=False,
            )

        assert exc_info.value.target_dir == "ios-main/edit-img"
        assert exc_info.value.conflicts == ("IMG_E0001.HEIC",)
        content = (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").read_text()
        assert content == "keep-me"
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")

    def test_video_conflict_leaves_images_unmoved(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_0002.MOV", "IMG_E0002.MOV"])
        write_files(tmp_path / "ios-main/edit-vid", ["IMG_E0002.MOV"])

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            fix_miscategorized(
                tmp_path,
                [MC],
                action=MiscategorizedAction.MV,
                dry_run=False,
            )

        assert exc_info.value.target_dir == "ios-main/edit-vid"
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert file_names(tmp_path / "ios-main/edit-img") == set()

    def test_conflict_in_one_source_leaves_every_source_unmoved(
        self,
        tmp_path: Path,
    ) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-nelu/orig-img", ["IMG_0002.HEIC", "IMG_E0002.HEIC"])
        write_files(tmp_path / "ios-nelu/edit-img", ["IMG_E0002.HEIC"])

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            run_fix_ios(tmp_path, dry_run=False, mv_miscategorized=True)

        assert exc_info.value.target_dir == "ios-nelu/edit-img"
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert file_names(tmp_path / "ios-main/edit-img") == set()
