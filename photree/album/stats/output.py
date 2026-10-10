"""Rich table formatting for album and gallery statistics.

Table cells are Rich markup: user-chosen names (media sources) are escaped
with ``markup_escape``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import rich.box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...common.formatting import indent, markup_escape
from ..store.media_source import MediaSourceType
from .models import (
    AggregateStats,
    AlbumsStats,
    AlbumStats,
    MediaSourceStats,
    MediaSourceTypeStats,
    SizeStats,
    YearStats,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")

_SIZE_STYLE = "cyan"
_TABLE_BOX = rich.box.SIMPLE


def _format_bytes(n: int) -> str:
    """Format *n* bytes as a human-readable string using binary (1024) units."""
    if n < 1024:
        return f"{n} B"
    value = float(n)
    for unit in _UNITS[1:]:
        value /= 1024
        if value < 1024 or unit == _UNITS[-1]:
            return f"{value:.1f} {unit}" if value >= 10 else f"{value:.2f} {unit}"
    return f"{value:.1f} {_UNITS[-1]}"


def _format_count(n: int) -> str:
    """Format an integer with thousands separators."""
    return f"{n:,}"


def _media_source_type_summary(
    by_type: tuple[MediaSourceTypeStats, ...],
) -> str:
    """Format media source type counts, e.g. ``'2 iOS, 1 std'``."""
    return ", ".join(f"{t.source_count} {t.media_source_type}" for t in by_type)


def _space_saved(agg: AggregateStats) -> tuple[int, float]:
    """Compute absolute and percentage space saved from optimization."""
    saved = agg.total.apparent_bytes - agg.total.on_disk_bytes
    pct = (
        (saved / agg.total.apparent_bytes * 100)
        if agg.total.apparent_bytes > 0
        else 0.0
    )
    return saved, pct


def _size_columns(table: Table) -> None:
    """Add the standard On-Disk / Size / Archive / Browsable / Derived / Cache column group."""
    table.add_column("On-Disk", justify="right", style=_SIZE_STYLE)
    table.add_column("Size", justify="right", style=_SIZE_STYLE)
    table.add_column("Archive", justify="right", style=_SIZE_STYLE)
    table.add_column("Browsable", justify="right", style=_SIZE_STYLE)
    table.add_column("Derived", justify="right", style=_SIZE_STYLE)
    table.add_column("Cache", justify="right", style=_SIZE_STYLE)


def _size_cells(
    total: int, on_disk: int, archive: int, derived: int, cache: int = 0
) -> tuple[str, str, str, str, str, str]:
    """Return (on_disk, size, archive, browsable, derived, cache) formatted strings."""
    browsable = total - archive - derived - cache
    return (
        _format_bytes(on_disk),
        _format_bytes(total),
        _format_bytes(archive),
        _format_bytes(browsable),
        _format_bytes(derived),
        _format_bytes(cache),
    )


def _bold_size_cells(
    total: int, on_disk: int, archive: int, derived: int, cache: int = 0
) -> tuple[str, str, str, str, str, str]:
    """Like ``_size_cells`` but wrapped in bold markup."""
    browsable = total - archive - derived - cache
    return (
        f"[bold]{_format_bytes(on_disk)}[/bold]",
        f"[bold]{_format_bytes(total)}[/bold]",
        f"[bold]{_format_bytes(archive)}[/bold]",
        f"[bold]{_format_bytes(browsable)}[/bold]",
        f"[bold]{_format_bytes(derived)}[/bold]",
        f"[bold]{_format_bytes(cache)}[/bold]",
    )


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------

_LEGEND_TERM_WIDTH = 13
_LEGEND_ENTRIES = (
    (
        "On-Disk",
        "Actual disk usage (inode-deduplicated; hardlinks and symlinks counted once)",
    ),
    ("Size", "Apparent size (naive sum of all file sizes)"),
    (
        "Archive",
        (
            "Original and edited files in archival directories"
            " (ios-{name}/ or std-{name}/)"
        ),
    ),
    (
        "Browsable",
        "Best-version files in {name}-img/ and {name}-vid/ (typically links to archive)",
    ),
    ("Derived", "JPEG conversions in {name}-jpg/"),
    ("Cache", "Derived data in .photree/cache/ (EXIF timestamps, face detection)"),
)
_LEGEND_FORMULA = " + ".join(
    f"[bold]{term}[/bold]" for term in ("Archive", "Browsable", "Derived", "Cache")
)

LEGEND = Text.from_markup(
    "\n".join(
        [
            "[bold]Legend[/bold]",
            *(
                indent(
                    f"[bold]{term}[/bold]"
                    f"{' ' * (_LEGEND_TERM_WIDTH - len(term))}{description}"
                )
                for term, description in _LEGEND_ENTRIES
            ),
            indent(f"[bold]Size[/bold] = {_LEGEND_FORMULA}"),
            indent(
                "[bold]Year[/bold]"
                f"{' ' * (_LEGEND_TERM_WIDTH - len('Year'))}"
                "Albums with date ranges are attributed to the start year"
            ),
        ]
    )
)


# ---------------------------------------------------------------------------
# Shared aggregate tables
# ---------------------------------------------------------------------------


def _cache_bytes(cache: SizeStats | None) -> int:
    return cache.apparent_bytes if cache is not None else 0


def _cache_on_disk(cache: SizeStats | None) -> int:
    return cache.on_disk_bytes if cache is not None else 0


def _cache_files(cache: SizeStats | None) -> int:
    return cache.file_count if cache is not None else 0


def _overview_counts(
    agg: AggregateStats,
    *,
    album_count: int | None,
    unique_media_source_names: tuple[str, ...] | None,
) -> list[tuple[str, str]]:
    """Key/value rows describing what the stats cover."""
    ms_desc = (
        f"{_format_count(agg.media_source_count)} "
        f"({_media_source_type_summary(agg.by_media_source_type)})"
    )
    unique_desc = (
        f" — {len(unique_media_source_names)} unique: "
        f"{markup_escape(', '.join(unique_media_source_names))}"
        if unique_media_source_names is not None
        else ""
    )
    return [
        *([("Albums", _format_count(album_count))] if album_count is not None else []),
        ("Media sources", ms_desc + unique_desc),
        ("Unique pictures", _format_count(agg.unique_pictures)),
        ("Unique videos", _format_count(agg.unique_videos)),
        *(
            [("Live Photos", _format_count(agg.unique_live_photos))]
            if agg.unique_live_photos > 0
            else []
        ),
    ]


def _overview_sizes(
    agg: AggregateStats, *, cache_storage: SizeStats | None
) -> list[tuple[str, str]]:
    """Key/value rows describing storage use."""
    cb = _cache_bytes(cache_storage)
    saved, pct = _space_saved(agg)
    browsable = (
        agg.total.apparent_bytes
        - agg.archive.apparent_bytes
        - agg.derived.apparent_bytes
    )

    def sized(text: str) -> str:
        return f"[{_SIZE_STYLE}]{text}[/{_SIZE_STYLE}]"

    return [
        (
            "Total files",
            _format_count(agg.total.file_count + _cache_files(cache_storage)),
        ),
        (
            "On-disk size",
            sized(
                _format_bytes(agg.total.on_disk_bytes + _cache_on_disk(cache_storage))
            ),
        ),
        ("Apparent size", sized(_format_bytes(agg.total.apparent_bytes + cb))),
        ("Space saved", sized(f"{_format_bytes(saved)} ({pct:.1f}%)")),
        ("Archive size", sized(_format_bytes(agg.archive.apparent_bytes))),
        ("Browsable size", sized(_format_bytes(browsable))),
        ("Derived size", sized(_format_bytes(agg.derived.apparent_bytes))),
        ("Cache size", sized(_format_bytes(cb))),
    ]


def _overview_panel(
    agg: AggregateStats,
    *,
    album_count: int | None = None,
    unique_media_source_names: tuple[str, ...] | None = None,
    cache_storage: SizeStats | None = None,
) -> Panel:
    """Key-value overview wrapped in a Panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value", justify="right")

    for key, value in [
        *_overview_counts(
            agg,
            album_count=album_count,
            unique_media_source_names=unique_media_source_names,
        ),
        *_overview_sizes(agg, cache_storage=cache_storage),
    ]:
        table.add_row(key, value)

    return Panel(table, title="[bold]Overview[/bold]", title_align="left", expand=False)


@dataclass(frozen=True)
class _Row:
    """The numbers of one size-table row, summable into a total row."""

    files: int
    apparent: int
    on_disk: int
    archive: int
    derived: int

    @staticmethod
    def total(rows: list[_Row]) -> _Row:
        return _Row(
            files=sum(r.files for r in rows),
            apparent=sum(r.apparent for r in rows),
            on_disk=sum(r.on_disk for r in rows),
            archive=sum(r.archive for r in rows),
            derived=sum(r.derived for r in rows),
        )


def _add_total_row(table: Table, total: _Row, cache_storage: SizeStats | None) -> None:
    """Close a size table with a bold total row that includes the cache."""
    cb = _cache_bytes(cache_storage)
    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{_format_count(total.files + _cache_files(cache_storage))}[/bold]",
        *_bold_size_cells(
            total.apparent + cb,
            total.on_disk + _cache_on_disk(cache_storage),
            total.archive,
            total.derived,
            cb,
        ),
    )


def _add_size_rows(table: Table, rows: list[tuple[str, _Row]]) -> None:
    for label, row in rows:
        table.add_row(
            label,
            _format_count(row.files),
            *_size_cells(row.apparent, row.on_disk, row.archive, row.derived),
        )


def _media_type_table(
    agg: AggregateStats, *, cache_storage: SizeStats | None = None
) -> Table:
    """Breakdown by media type (images / videos / sidecars)."""
    table = Table(title="By Media Type", box=_TABLE_BOX)
    table.add_column("Type")
    table.add_column("Files", justify="right")
    _size_columns(table)

    rows = [
        (
            label,
            _Row(
                files=rb.total.file_count,
                apparent=rb.total.apparent_bytes,
                on_disk=rb.total.on_disk_bytes,
                archive=rb.archive.apparent_bytes,
                derived=rb.derived.apparent_bytes,
            ),
        )
        for label, rb in [
            ("Images", agg.images),
            ("Videos", agg.videos),
            ("Sidecars", agg.sidecars),
        ]
    ]
    _add_size_rows(table, rows)
    _add_total_row(table, _Row.total([row for _, row in rows]), cache_storage)
    return table


def _source_type_table(agg: AggregateStats) -> Table:
    """Breakdown by media source type (iOS / std)."""
    table = Table(title="By Media Source Type", box=_TABLE_BOX)
    table.add_column("Type")
    table.add_column("Files", justify="right")
    _size_columns(table)

    labels = {MediaSourceType.IOS: "iOS", MediaSourceType.STD: "Std"}
    for t in agg.by_media_source_type:
        table.add_row(
            f"{labels[t.media_source_type]} ({t.source_count})",
            _format_count(t.total.file_count),
            *_size_cells(
                t.total.apparent_bytes,
                t.total.on_disk_bytes,
                t.archive.apparent_bytes,
                t.derived.apparent_bytes,
            ),
        )

    return table


def _per_media_source_table(
    media_sources: tuple[MediaSourceStats, ...],
) -> Table:
    """One row per media source."""
    table = Table(title="By Media Source", box=_TABLE_BOX)
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("Files", justify="right")
    _size_columns(table)

    for ms in media_sources:
        table.add_row(
            markup_escape(ms.name),
            str(ms.media_source_type),
            _format_count(ms.total.file_count),
            *_size_cells(
                ms.total.apparent_bytes,
                ms.total.on_disk_bytes,
                ms.archive.apparent_bytes,
                ms.derived.apparent_bytes,
            ),
        )

    return table


def _format_table(
    agg: AggregateStats, *, cache_storage: SizeStats | None = None
) -> Table:
    """Breakdown by file extension, sorted by size descending."""
    table = Table(title="By Format", box=_TABLE_BOX)
    table.add_column("Format")
    table.add_column("Files", justify="right")
    _size_columns(table)

    rows = [
        (
            fs.extension,
            _Row(
                files=fs.file_count,
                apparent=fs.apparent_bytes,
                on_disk=fs.on_disk_bytes,
                archive=fs.archive_bytes,
                derived=fs.derived_bytes,
            ),
        )
        for fs in agg.by_format
    ]
    _add_size_rows(table, rows)
    _add_total_row(table, _Row.total([row for _, row in rows]), cache_storage)
    return table


def _format_aggregate_tables(
    agg: AggregateStats,
    *,
    album_count: int | None = None,
    unique_media_source_names: tuple[str, ...] | None = None,
    media_sources: tuple[MediaSourceStats, ...] | None = None,
    cache_storage: SizeStats | None = None,
) -> list[Panel | Table | Text]:
    """Build the shared set of tables from ``AggregateStats``."""
    sep = Text("")
    return [
        _overview_panel(
            agg,
            album_count=album_count,
            unique_media_source_names=unique_media_source_names,
            cache_storage=cache_storage,
        ),
        sep,
        _media_type_table(agg, cache_storage=cache_storage),
        sep,
        (
            _per_media_source_table(media_sources)
            if media_sources
            else _source_type_table(agg)
        ),
        sep,
        _format_table(agg, cache_storage=cache_storage),
    ]


# ---------------------------------------------------------------------------
# Year breakdown table (gallery only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _YearRow:
    year: str
    albums: int
    pictures: int
    videos: int
    sizes: _Row
    cache: int


def _year_row(ys: YearStats) -> _YearRow:
    a = ys.aggregate
    cb = _cache_bytes(ys.cache_storage)
    return _YearRow(
        year=ys.year,
        albums=ys.album_count,
        pictures=a.unique_pictures,
        videos=a.unique_videos,
        sizes=_Row(
            files=0,  # the year table shows counts, not file numbers
            apparent=a.total.apparent_bytes + cb,
            on_disk=a.total.on_disk_bytes + _cache_on_disk(ys.cache_storage),
            archive=a.archive.apparent_bytes,
            derived=a.derived.apparent_bytes,
        ),
        cache=cb,
    )


def _year_table(by_year: tuple[YearStats, ...]) -> Table:
    """Per-year summary table for gallery stats."""
    table = Table(title="By Year", box=_TABLE_BOX)
    table.add_column("Year")
    table.add_column("Albums", justify="right")
    table.add_column("Pictures", justify="right")
    table.add_column("Videos", justify="right")
    _size_columns(table)

    rows = [_year_row(ys) for ys in by_year]
    for r in rows:
        table.add_row(
            r.year,
            _format_count(r.albums),
            _format_count(r.pictures),
            _format_count(r.videos),
            *_size_cells(
                r.sizes.apparent,
                r.sizes.on_disk,
                r.sizes.archive,
                r.sizes.derived,
                r.cache,
            ),
        )

    _add_year_total_row(table, rows)
    return table


def _add_year_total_row(table: Table, rows: list[_YearRow]) -> None:
    total = _Row.total([r.sizes for r in rows])
    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{_format_count(sum(r.albums for r in rows))}[/bold]",
        f"[bold]{_format_count(sum(r.pictures for r in rows))}[/bold]",
        f"[bold]{_format_count(sum(r.videos for r in rows))}[/bold]",
        *_bold_size_cells(
            total.apparent,
            total.on_disk,
            total.archive,
            total.derived,
            sum(r.cache for r in rows),
        ),
    )


# ---------------------------------------------------------------------------
# Public formatting functions
# ---------------------------------------------------------------------------


def format_album_stats(stats: AlbumStats) -> Group:
    """Format album-level statistics as a Rich renderable."""
    return with_legend(
        _format_aggregate_tables(
            stats.aggregate,
            media_sources=stats.by_media_source,
            cache_storage=stats.cache_storage,
        )
    )


def albums_stats_renderables(
    stats: AlbumsStats, *, cache_storage: SizeStats | None = None
) -> Sequence[RenderableType]:
    """Everything in an albums-stats report except the trailing legend.

    Exposed so the gallery report can insert its collection section between
    the year table and the legend without duplicating the tables above it.
    *cache_storage* overrides the value on *stats*, which is how the gallery
    folds its own face-index storage into the same row.
    """
    return [
        *_format_aggregate_tables(
            stats.aggregate,
            album_count=stats.album_count,
            unique_media_source_names=stats.unique_media_source_names,
            cache_storage=cache_storage
            if cache_storage is not None
            else stats.cache_storage,
        ),
        *([Text(""), _year_table(stats.by_year)] if stats.by_year else []),
    ]


def with_legend(renderables: Sequence[RenderableType]) -> Group:
    """Close a stats report with the shared legend."""
    return Group(*renderables, Text(""), LEGEND)


def format_albums_stats(stats: AlbumsStats) -> Group:
    """Format statistics for a set of albums as a Rich renderable."""
    return with_legend(albums_stats_renderables(stats))
