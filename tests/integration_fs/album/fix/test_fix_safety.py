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
    MiscategorizedMoveConflictError,
    mv_miscategorized,
    prefer_higher_quality_when_dups,
    run_fix_ios,
)
from photree.album.fix.ios import (
    validate_fix_flags as validate_fix_ios_flags,
)
from photree.album.fix.ios.output import format_fix_ios_result
from photree.album.fix.output import format_fix_result
from photree.album.fix.rm_upstream import MediaKind
from photree.album.store.protocol import MAIN_MEDIA_SOURCE, std_media_source
from photree.fsprotocol import LinkMode

MC = MAIN_MEDIA_SOURCE
STD = std_media_source("nelu")


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {f.name for f in directory.iterdir() if f.is_file()}


def _ios_album_without_jpg(album: Path) -> None:
    _setup_dir(album / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
    _setup_dir(album / "main-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])


# ---------------------------------------------------------------------------
# rm-upstream: missing/empty signal directories
# ---------------------------------------------------------------------------


class TestRmUpstreamSignals:
    def test_missing_jpg_dir_deletes_nothing(self, tmp_path: Path) -> None:
        """--skip-heic-to-jpeg leaves no main-jpg: that is not a deletion."""
        _ios_album_without_jpg(tmp_path)

        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_orig == ()
        assert _names(tmp_path / "ios-main/orig-img") == {
            "IMG_0001.HEIC",
            "IMG_0002.HEIC",
        }
        assert [(s.directory, s.reason) for s in result.skipped] == [
            ("main-jpg", SignalSkipReason.MISSING),
            ("main-vid", SignalSkipReason.MISSING),
        ]

    def test_empty_jpg_dir_deletes_nothing(self, tmp_path: Path) -> None:
        _ios_album_without_jpg(tmp_path)
        _setup_dir(tmp_path / "main-jpg", [])

        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_orig == ()
        assert len(_names(tmp_path / "ios-main/orig-img")) == 2
        assert ("main-jpg", SignalSkipReason.NO_EXPECTED_FILES) in [
            (s.directory, s.reason) for s in result.skipped
        ]

    def test_missing_vid_dir_deletes_no_video(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        _setup_dir(tmp_path / "std-nelu/edit-vid", ["clip.mov"])

        result = rm_upstream(tmp_path, STD)

        assert result.mov.removed_orig == ()
        assert _names(tmp_path / "std-nelu/orig-vid") == {"clip.mov", "other.mov"}
        assert ("nelu-vid", SignalSkipReason.MISSING) in [
            (s.directory, s.reason) for s in result.skipped
        ]

    def test_skip_is_reported_in_fix_output(self, tmp_path: Path) -> None:
        _ios_album_without_jpg(tmp_path)

        lines = format_fix_result(
            run_fix(
                tmp_path,
                link_mode=LinkMode.HARDLINK,
                dry_run=False,
                rm_upstream_flag=True,
            )
        )

        assert any("main-jpg" in line and "missing" in line for line in lines)


# ---------------------------------------------------------------------------
# rm-upstream: refusing to empty an archive
# ---------------------------------------------------------------------------


class TestRmUpstreamAllKeysRefusal:
    def test_emptied_vid_dir_is_refused(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        _setup_dir(tmp_path / "nelu-vid", [])

        with pytest.raises(RmUpstreamRefusedError) as exc_info:
            rm_upstream(tmp_path, STD)

        assert exc_info.value.media_source == "nelu"
        assert exc_info.value.kind == MediaKind.VIDEOS
        assert exc_info.value.key_count == 2
        assert _names(tmp_path / "std-nelu/orig-vid") == {"clip.mov", "other.mov"}

    def test_emptied_img_dir_is_refused(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        _setup_dir(tmp_path / "main-img", [])
        _setup_dir(tmp_path / "main-jpg", ["IMG_0001.jpg", "IMG_0002.jpg"])

        with pytest.raises(RmUpstreamRefusedError) as exc_info:
            rm_upstream(tmp_path, MC)

        assert exc_info.value.kind == MediaKind.IMAGES
        assert len(_names(tmp_path / "ios-main/orig-img")) == 2
        assert len(_names(tmp_path / "main-jpg")) == 2

    def test_force_overrides_refusal(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        _setup_dir(tmp_path / "nelu-vid", [])

        result = rm_upstream(tmp_path, STD, force=True)

        assert result.mov.removed_orig == ("clip.mov",)

    def test_run_fix_refusal_leaves_other_sources_untouched(
        self, tmp_path: Path
    ) -> None:
        """All sources are planned first: one refusal means no deletion at all."""
        # "main" has a legitimate deletion, "nelu" would be emptied.
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        _setup_dir(tmp_path / "nelu-vid", [])

        with pytest.raises(RmUpstreamRefusedError):
            run_fix(
                tmp_path,
                link_mode=LinkMode.HARDLINK,
                dry_run=False,
                rm_upstream_flag=True,
            )

        assert "IMG_0002.HEIC" in _names(tmp_path / "ios-main/orig-img")


# ---------------------------------------------------------------------------
# run_fix / run_fix_ios reporting
# ---------------------------------------------------------------------------


class TestFixReporting:
    def test_no_orphans_found_is_reported(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])

        result = run_fix(
            tmp_path, link_mode=LinkMode.HARDLINK, dry_run=False, rm_orphan_flag=True
        )

        assert result.rm_orphan_removed_by_dir == ()
        assert format_fix_result(result) == ["Done. No orphans found."]

    def test_no_media_sources_is_reported(self, tmp_path: Path) -> None:
        result = run_fix(
            tmp_path, link_mode=LinkMode.HARDLINK, dry_run=False, rm_orphan_flag=True
        )

        assert result.no_media_sources
        assert format_fix_result(result) == ["No media sources found; nothing to fix."]

    def test_no_duplicates_found_is_reported(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])

        result = run_fix_ios(
            tmp_path, dry_run=False, prefer_higher_quality_when_dups=True
        )

        assert format_fix_ios_result(result) == ["Done. No duplicates found."]

    def test_no_ios_media_sources_is_reported(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])

        result = run_fix_ios(tmp_path, dry_run=False, rm_orphan_sidecar=True)

        assert result.no_ios_media_sources
        assert format_fix_ios_result(result) == [
            "No iOS media sources found; nothing to fix."
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
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0235.DNG", "IMG_0235.HEIC", "IMG_0235.JPG"],
        )

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert _names(tmp_path / "ios-main/orig-img") == {"IMG_0235.DNG"}
        assert result.removed_by_dir == (
            ("orig-img", ("IMG_0235.HEIC", "IMG_0235.JPG")),
        )

    def test_keeps_heic_over_heif(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.HEIF"])

        prefer_higher_quality_when_dups(tmp_path, MC)

        assert _names(tmp_path / "ios-main/orig-img") == {"IMG_0001.HEIC"}


class TestMvMiscategorizedOverwrite:
    def test_refuses_to_overwrite_existing_target(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").write_text("keep-me")

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            mv_miscategorized(tmp_path, MC)

        assert exc_info.value.target_dir == "edit-img"
        assert exc_info.value.conflicts == ("IMG_E0001.HEIC",)
        content = (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").read_text()
        assert content == "keep-me"
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
