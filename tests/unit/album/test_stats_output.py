import re
from dataclasses import replace
from io import StringIO

import pytest
from rich.console import Console, RenderableType

from photree.album.cli.stats_output import (
    format_album_stats,
    format_albums_stats,
    format_bytes,
)
from photree.album.stats.models import SizeStats
from photree.album.stats.testkit import ALBUM_STATS, ALBUMS_STATS

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


def _render(renderable: RenderableType) -> str:
    out = StringIO()
    Console(file=out, width=200, color_system=None).print(renderable)
    return out.getvalue()


def _rows(text: str, label: str) -> list[list[str]]:
    """Return the cells of every table row whose first cell is *label*."""
    return [
        cells
        for cells in (
            [c for c in re.split(r"\s{2,}", line.strip(" │")) if c]
            for line in text.splitlines()
        )
        if cells and cells[0] == label
    ]


def _row(text: str, label: str) -> list[str]:
    return _rows(text, label)[0]


class TestFormatAlbumStats:
    def test_overview_shows_album_totals(self) -> None:
        text = _render(format_album_stats(ALBUM_STATS))

        assert _row(text, "Total files")[-1] == "2,028"
        assert _row(text, "On-disk size")[-1] == "38.3 GiB"
        assert _row(text, "Apparent size")[-1] == "54.5 GiB"
        assert _row(text, "Space saved")[-1] == "16.2 GiB (29.7%)"

    def test_media_type_total_row_sums_the_types(self) -> None:
        text = _render(format_album_stats(ALBUM_STATS))

        assert _row(text, "Total")[:3] == ["Total", "2,028", "37.0 GiB"]

    def test_totals_include_the_cache(self) -> None:
        cache = SizeStats(file_count=12, apparent_bytes=_GIB, on_disk_bytes=_GIB)
        text = _render(format_album_stats(replace(ALBUM_STATS, cache_storage=cache)))

        assert _row(text, "Total files")[-1] == "2,040"
        assert _row(text, "Cache size")[-1] == "1.00 GiB"
        assert _row(text, "Total")[1] == "2,040"
        assert _row(text, "Total")[-1] == "1.00 GiB"

    def test_media_source_names_are_escaped(self) -> None:
        bracketed = replace(ALBUM_STATS.by_media_source[0], name="main [old]")
        stats = replace(
            ALBUM_STATS,
            by_media_source=(bracketed, *ALBUM_STATS.by_media_source[1:]),
        )

        assert _row(_render(format_album_stats(stats)), "main [old]")[1] == "ios"

    def test_album_stats_end_with_the_legend(self) -> None:
        text = _render(format_album_stats(ALBUM_STATS))

        assert text.rstrip().splitlines()[-1].strip().startswith("Year")


class TestFormatAlbumsStats:
    def test_overview_counts_albums_and_media_sources(self) -> None:
        text = _render(format_albums_stats(ALBUMS_STATS))

        assert _row(text, "Albums")[-1] == "3"
        assert _row(text, "Media sources")[-1] == (
            "4 (3 ios, 1 std) — 2 unique: main, nelu"
        )

    def test_year_table_has_a_row_per_year_and_a_total(self) -> None:
        text = _render(format_albums_stats(ALBUMS_STATS))

        assert _row(text, "2024")[:4] == ["2024", "2", "806", "56"]
        assert _row(text, "2025")[:4] == ["2025", "1", "145", "10"]
        assert _rows(text, "Total")[-1][:5] == ["Total", "3", "951", "66", "80.9 GiB"]
