import pytest

from photree.album.stats.output import format_bytes

_KIB = 1024
_MIB = 1024**2
_GIB = 1024**3
_TIB = 1024**4


class TestFormatBytes:
    @pytest.mark.parametrize(
        ("n", "expected"),
        [
            (0, "0 B"),
            (1023, "1023 B"),
            (_KIB, "1.00 KiB"),
            (1536, "1.50 KiB"),
            (10 * _KIB - 1, "10.0 KiB"),
            (10 * _KIB, "10.0 KiB"),
            (_MIB - 1, "1.00 MiB"),
            (_MIB, "1.00 MiB"),
            (_GIB - 1, "1.00 GiB"),
            (_TIB - 1, "1.00 TiB"),
            (5000 * _TIB, "5000.0 TiB"),
        ],
    )
    def test_format_bytes_picks_unit_and_decimals_from_rounded_value(
        self,
        n: int,
        expected: str,
    ) -> None:
        assert format_bytes(n) == expected
