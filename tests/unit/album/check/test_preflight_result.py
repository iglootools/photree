from dataclasses import replace
from typing import Any

import pytest

from photree.album.check import (
    AlbumCheckFailureKind,
    AlbumCheckWarningKind,
    AlbumDirCheck,
    AlbumIdCheck,
    AlbumPreflightResult,
)
from photree.album.check.exif_cache_state import ExifCacheStateCheck
from photree.album.check.exif_date import AlbumNamingResult
from photree.album.check.face_state import FaceStateCheck
from photree.album.check.media_metadata import MediaMetadataCheck
from photree.album.check.testkit import (
    INTEGRITY_FAILURES,
    JPEG_INTEGRITY_FAILURES,
    PREFLIGHT_EXIF_WARNING,
    PREFLIGHT_OK,
    PREFLIGHT_SIDECAR_WARNING,
)
from photree.album.check.unexpected_dirs import UnexpectedDirsCheck
from photree.album.naming import check_album_naming

# One failing value per check, each applied alone to an album that passes.
_FAILING_CHECKS: tuple[tuple[AlbumCheckFailureKind, dict[str, Any]], ...] = (
    (
        AlbumCheckFailureKind.MEDIA_SOURCE_CONFLICT,
        {"media_source_conflicts": ("main",)},
    ),
    (
        AlbumCheckFailureKind.MISSING_DIRS,
        {"dir_check": AlbumDirCheck(present=("main-img",), missing=("main-jpg",))},
    ),
    (
        AlbumCheckFailureKind.MISSING_ALBUM_ID,
        {"album_id_check": AlbumIdCheck(has_id=False)},
    ),
    (
        AlbumCheckFailureKind.UNEXPECTED_DIRS,
        {"unexpected_dirs_check": UnexpectedDirsCheck(unexpected=("stray",))},
    ),
    (
        AlbumCheckFailureKind.STALE_MEDIA_METADATA,
        {"media_metadata_check": MediaMetadataCheck(has_media_metadata=False)},
    ),
    (AlbumCheckFailureKind.INTEGRITY, {"integrity": INTEGRITY_FAILURES}),
    (AlbumCheckFailureKind.JPEG, {"jpeg_check": JPEG_INTEGRITY_FAILURES}),
    (
        AlbumCheckFailureKind.NAMING,
        {
            "naming": AlbumNamingResult(
                parsed=None,
                issues=check_album_naming("Beach"),
                exif_check=None,
            ),
        },
    ),
    (
        AlbumCheckFailureKind.STALE_FACE_STATE,
        {
            "face_state_check": FaceStateCheck(
                model_mismatch=True,
                npz_yaml_sync_errors=(),
            ),
        },
    ),
    (
        AlbumCheckFailureKind.STALE_EXIF_CACHE,
        {"exif_cache_check": ExifCacheStateCheck(missing_sources=("main",))},
    ),
)


class TestFailures:
    def test_clean_album_has_no_failures(self) -> None:
        assert PREFLIGHT_OK.success
        assert PREFLIGHT_OK.failures == ()

    @pytest.mark.parametrize(
        ("kind", "failing"),
        _FAILING_CHECKS,
        ids=[kind.value for kind, _ in _FAILING_CHECKS],
    )
    def test_a_single_failed_check_fails_the_album_and_names_it(
        self,
        kind: AlbumCheckFailureKind,
        failing: dict[str, Any],
    ) -> None:
        result = replace(PREFLIGHT_OK, **failing)

        assert not result.success
        assert result.failures == (kind,)

    def test_every_failure_kind_has_a_failing_case(self) -> None:
        assert {kind for kind, _ in _FAILING_CHECKS} == set(AlbumCheckFailureKind)


class TestWarnings:
    def test_clean_album_has_no_warnings(self) -> None:
        assert not PREFLIGHT_OK.has_warnings

    @pytest.mark.parametrize(
        "result",
        [PREFLIGHT_SIDECAR_WARNING, PREFLIGHT_EXIF_WARNING],
    )
    def test_warnings_do_not_fail_the_check(self, result: AlbumPreflightResult) -> None:
        assert result.success
        assert result.has_warnings


class TestFatalWarnings:
    @pytest.mark.parametrize(
        ("result", "fatal_sidecar", "fatal_exif", "expected"),
        [
            (PREFLIGHT_OK, True, True, False),
            (PREFLIGHT_SIDECAR_WARNING, False, False, False),
            (PREFLIGHT_SIDECAR_WARNING, True, False, True),
            (PREFLIGHT_SIDECAR_WARNING, False, True, False),
            (PREFLIGHT_EXIF_WARNING, False, False, False),
            (PREFLIGHT_EXIF_WARNING, False, True, True),
            (PREFLIGHT_EXIF_WARNING, True, False, False),
        ],
    )
    def test_a_warning_is_fatal_only_under_its_own_flag(
        self,
        result: AlbumPreflightResult,
        *,
        fatal_sidecar: bool,
        fatal_exif: bool,
        expected: bool,
    ) -> None:
        assert (
            result.has_fatal_warnings(
                fatal_sidecar=fatal_sidecar,
                fatal_exif=fatal_exif,
            )
            is expected
        )

    @pytest.mark.parametrize(
        ("result", "warning"),
        [
            (PREFLIGHT_SIDECAR_WARNING, AlbumCheckWarningKind.MISSING_SIDECARS),
            (PREFLIGHT_EXIF_WARNING, AlbumCheckWarningKind.EXIF_DATE_MISMATCH),
        ],
    )
    def test_fatal_flags_move_a_warning_to_the_fatal_list(
        self,
        result: AlbumPreflightResult,
        warning: AlbumCheckWarningKind,
    ) -> None:
        assert result.fatal_warnings(fatal_sidecar=True, fatal_exif=True) == (warning,)
        assert result.non_fatal_warnings(fatal_sidecar=True, fatal_exif=True) == ()
        assert result.fatal_warnings(fatal_sidecar=False, fatal_exif=False) == ()
        assert result.non_fatal_warnings(fatal_sidecar=False, fatal_exif=False) == (
            warning,
        )
