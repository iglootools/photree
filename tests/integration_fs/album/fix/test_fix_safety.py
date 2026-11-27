"""Regression tests for destructive fix operations: refusals and skipped signals."""

from pathlib import Path

import pytest

from photree.album.fix import (
    FixValidationError,
    FixValidationErrorKind,
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
from photree.album.store.media_source import MAIN_MEDIA_SOURCE, std_media_source
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
