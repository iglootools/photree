import pytest

from photree.album.check import AlbumCheckWarningKind, AlbumPreflightResult
from photree.album.check.testkit import (
    PREFLIGHT_EXIF_WARNING,
    PREFLIGHT_OK,
    PREFLIGHT_SIDECAR_WARNING,
)


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
