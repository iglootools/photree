from photree.albums.batchcli.check import check_retry_flags
from photree.common.formatting import format_flags


class TestCheckRetryFlags:
    def test_default_run_repeats_no_flag(self) -> None:
        flags = check_retry_flags(
            checksum=True,
            fatal_warnings=False,
            fatal_sidecar=False,
            fatal_exif_date_match=True,
            check_naming=True,
            check_date_part_collision=True,
            check_exif_date_match=True,
            refresh_exif_cache=False,
        )

        assert format_flags(flags) == ""

    def test_every_option_the_run_changed_is_repeated(self) -> None:
        flags = check_retry_flags(
            checksum=False,
            fatal_warnings=True,
            fatal_sidecar=True,
            fatal_exif_date_match=False,
            check_naming=False,
            check_date_part_collision=False,
            check_exif_date_match=False,
            refresh_exif_cache=True,
        )

        assert format_flags(flags) == (
            " --no-checksum --fatal-warnings --fatal-sidecar"
            " --no-fatal-exif-date-match --no-check-naming"
            " --no-check-date-part-collision --no-check-exif-date-match"
            " --refresh-exif-cache"
        )
