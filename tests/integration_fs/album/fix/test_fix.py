from pathlib import Path

import pytest

from photree.album.fix import (
    FixValidationError,
    FixValidationErrorKind,
    run_fix,
    validate_fix_flags,
)
from photree.album.fix.ios import (
    FixIosValidationError,
    FixIosValidationErrorKind,
    run_fix_ios,
    validate_fix_flags as validate_fix_ios_flags,
)
from photree.album.fix.ios.output import format_fix_ios_result
from photree.album.fix.output import format_fix_result
from tests.testkit import write_files


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
            "[dry-run] Would remove 1 orphan(s): 1 from edit-img.",
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
