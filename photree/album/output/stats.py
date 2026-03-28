"""Rich table formatting for album and gallery statistics."""

from __future__ import annotations

import rich.box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...fsprotocol import MediaSourceType
from ..stats import (
    AggregateStats,
    AlbumStats,
    GalleryStats,
    MediaSourceStats,
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
    by_type: tuple[tuple[MediaSourceType, int], ...],
) -> str:
    """Format media source type counts, e.g. ``'2 iOS, 1 plain'``."""
    return ", ".join(f"{count} {mst}" for mst, count in by_type)


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
    """Add the standard On-Disk / Size / Archive / Browsable / Derived column group."""
    table.add_column("On-Disk", justify="right", style=_SIZE_STYLE)
    table.add_column("Size", justify="right", style=_SIZE_STYLE)
    table.add_column("Archive", justify="right", style=_SIZE_STYLE)
    table.add_column("Browsable", justify="right", style=_SIZE_STYLE)
    table.add_column("Derived", justify="right", style=_SIZE_STYLE)


def _size_cells(
    total: int, on_disk: int, archive: int, derived: int
) -> tuple[str, str, str, str, str]:
    """Return (on_disk, size, archive, browsable, derived) formatted strings."""
    browsable = total - archive - derived
    return (
        _format_bytes(on_disk),
        _format_bytes(total),
        _format_bytes(archive),
        _format_bytes(browsable),
        _format_bytes(derived),
    )


def _bold_size_cells(
    total: int, on_disk: int, archive: int, derived: int
) -> tuple[str, str, str, str, str]:
    """Like ``_size_cells`` but wrapped in bold markup."""
    browsable = total - archive - derived
    return (
        f"[bold]{_format_bytes(on_disk)}[/bold]",
        f"[bold]{_format_bytes(total)}[/bold]",
        f"[bold]{_format_bytes(archive)}[/bold]",
        f"[bold]{_format_bytes(browsable)}[/bold]",
        f"[bold]{_format_bytes(derived)}[/bold]",
    )


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------

_LEGEND = Text.from_markup(
    "[bold]Legend[/bold]\n"
    "  [bold]On-Disk[/bold]    Actual disk usage (inode-deduplicated; hardlinks and symlinks counted once)\n"
    "  [bold]Size[/bold]       Apparent size (naive sum of all file sizes)\n"
    "  [bold]Archive[/bold]    Original and edited files in ios-{{name}}/ archival directories\n"
    "  [bold]Browsable[/bold]  Best-version files in {{name}}-img/ and {{name}}-vid/ (typically links to archive)\n"
    "  [bold]Derived[/bold]    JPEG conversions in {{name}}-jpg/\n"
    "  [bold]Size[/bold] = [bold]Archive[/bold] + [bold]Browsable[/bold] + [bold]Derived[/bold]\n"
    "  [bold]Year[/bold]       Albums with date ranges are attributed to the start year"
)


# ---------------------------------------------------------------------------
# Shared aggregate tables
# ---------------------------------------------------------------------------


def _overview_panel(
    agg: AggregateStats,
    *,
    album_count: int | None = None,
    unique_media_source_names: tuple[str, ...] | None = None,
) -> Panel:
    """Key-value overview wrapped in a Panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value", justify="right")

    if album_count is not None:
        table.add_row("Albums", _format_count(album_count))

    ms_desc = f"{_format_count(agg.media_source_count)} ({_media_source_type_summary(agg.by_media_source_type)})"
    if unique_media_source_names is not None:
        ms_desc += f" — {len(unique_media_source_names)} unique: {', '.join(unique_media_source_names)}"
    table.add_row("Media sources", ms_desc)

    table.add_row("Unique pictures", _format_count(agg.unique_pictures))
    table.add_row("Unique videos", _format_count(agg.unique_videos))
    table.add_row("Total files", _format_count(agg.total.file_count))

    cs = _SIZE_STYLE
    table.add_row(
        "On-disk size", f"[{cs}]{_format_bytes(agg.total.on_disk_bytes)}[/{cs}]"
    )
    table.add_row(
        "Apparent size", f"[{cs}]{_format_bytes(agg.total.apparent_bytes)}[/{cs}]"
    )

    saved, pct = _space_saved(agg)
    table.add_row("Space saved", f"[{cs}]{_format_bytes(saved)} ({pct:.1f}%)[/{cs}]")

    browsable = (
        agg.total.apparent_bytes
        - agg.archive.apparent_bytes
        - agg.derived.apparent_bytes
    )
    table.add_row(
        "Archive size", f"[{cs}]{_format_bytes(agg.archive.apparent_bytes)}[/{cs}]"
    )
    table.add_row("Browsable size", f"[{cs}]{_format_bytes(browsable)}[/{cs}]")
    table.add_row(
        "Derived size", f"[{cs}]{_format_bytes(agg.derived.apparent_bytes)}[/{cs}]"
    )

    return Panel(table, title="[bold]Overview[/bold]", title_align="left", expand=False)


def _media_type_table(agg: AggregateStats) -> Table:
    """Breakdown by media type (images / videos / sidecars)."""
    table = Table(title="By Media Type", box=_TABLE_BOX)
    table.add_column("Type")
    table.add_column("Files", justify="right")
    _size_columns(table)

    total_files = 0
    total_bytes = 0
    total_on_disk = 0
    total_archive = 0
    total_derived = 0
    for label, rb in [
        ("Images", agg.images),
        ("Videos", agg.videos),
        ("Sidecars", agg.sidecars),
    ]:
        table.add_row(
            label,
            _format_count(rb.total.file_count),
            *_size_cells(
                rb.total.apparent_bytes,
                rb.total.on_disk_bytes,
                rb.archive.apparent_bytes,
                rb.derived.apparent_bytes,
            ),
        )
        total_files += rb.total.file_count
        total_bytes += rb.total.apparent_bytes
        total_on_disk += rb.total.on_disk_bytes
        total_archive += rb.archive.apparent_bytes
        total_derived += rb.derived.apparent_bytes

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{_format_count(total_files)}[/bold]",
        *_bold_size_cells(total_bytes, total_on_disk, total_archive, total_derived),
    )

    return table


def _source_type_table(agg: AggregateStats) -> Table:
    """Breakdown by media source type (iOS / plain)."""
    table = Table(title="By Media Source Type", box=_TABLE_BOX)
    table.add_column("Type")
    table.add_column("Files", justify="right")
    _size_columns(table)

    ios_count = sum(
        c for mst, c in agg.by_media_source_type if mst == MediaSourceType.IOS
    )
    plain_count = sum(
        c for mst, c in agg.by_media_source_type if mst == MediaSourceType.PLAIN
    )

    if ios_count > 0:
        ios_total = (
            agg.archive.apparent_bytes
            + agg.original.apparent_bytes
            + agg.derived.apparent_bytes
        )
        ios_on_disk = (
            agg.archive.on_disk_bytes
            + agg.original.on_disk_bytes
            + agg.derived.on_disk_bytes
        )
        table.add_row(
            f"iOS ({ios_count})",
            _format_count(
                agg.archive.file_count
                + agg.original.file_count
                + agg.derived.file_count
            ),
            *_size_cells(
                ios_total,
                ios_on_disk,
                agg.archive.apparent_bytes,
                agg.derived.apparent_bytes,
            ),
        )
    if plain_count > 0:
        plain_total = agg.original.apparent_bytes + agg.derived.apparent_bytes
        plain_on_disk = agg.original.on_disk_bytes + agg.derived.on_disk_bytes
        table.add_row(
            f"Plain ({plain_count})",
            _format_count(agg.original.file_count + agg.derived.file_count),
            *_size_cells(plain_total, plain_on_disk, 0, agg.derived.apparent_bytes),
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
        archive = (
            ms.archive.apparent_bytes
            if ms.media_source_type == MediaSourceType.IOS
            else 0
        )
        table.add_row(
            ms.name,
            str(ms.media_source_type),
            _format_count(ms.total.file_count),
            *_size_cells(
                ms.total.apparent_bytes,
                ms.total.on_disk_bytes,
                archive,
                ms.derived.apparent_bytes,
            ),
        )

    return table


def _format_table(agg: AggregateStats) -> Table:
    """Breakdown by file extension, sorted by size descending."""
    table = Table(title="By Format", box=_TABLE_BOX)
    table.add_column("Format")
    table.add_column("Files", justify="right")
    _size_columns(table)

    total_files = 0
    total_bytes = 0
    total_on_disk = 0
    total_archive = 0
    total_derived = 0
    for fs in agg.by_format:
        table.add_row(
            fs.extension,
            _format_count(fs.file_count),
            *_size_cells(
                fs.apparent_bytes, fs.on_disk_bytes, fs.archive_bytes, fs.derived_bytes
            ),
        )
        total_files += fs.file_count
        total_bytes += fs.apparent_bytes
        total_on_disk += fs.on_disk_bytes
        total_archive += fs.archive_bytes
        total_derived += fs.derived_bytes

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{_format_count(total_files)}[/bold]",
        *_bold_size_cells(total_bytes, total_on_disk, total_archive, total_derived),
    )

    return table


def _format_aggregate_tables(
    agg: AggregateStats,
    *,
    album_count: int | None = None,
    unique_media_source_names: tuple[str, ...] | None = None,
    media_sources: tuple[MediaSourceStats, ...] | None = None,
) -> list[Panel | Table | Text]:
    """Build the shared set of tables from ``AggregateStats``."""
    sep = Text("")
    renderables: list[Panel | Table | Text] = [
        _overview_panel(
            agg,
            album_count=album_count,
            unique_media_source_names=unique_media_source_names,
        ),
        sep,
        _media_type_table(agg),
        sep,
    ]

    if media_sources is not None and len(media_sources) > 0:
        renderables.append(_per_media_source_table(media_sources))
    else:
        renderables.append(_source_type_table(agg))

    renderables.append(sep)
    renderables.append(_format_table(agg))
    return renderables


# ---------------------------------------------------------------------------
# Year breakdown table (gallery only)
# ---------------------------------------------------------------------------


def _year_table(by_year: tuple[YearStats, ...]) -> Table:
    """Per-year summary table for gallery stats."""
    table = Table(title="By Year", box=_TABLE_BOX)
    table.add_column("Year")
    table.add_column("Albums", justify="right")
    table.add_column("Pictures", justify="right")
    table.add_column("Videos", justify="right")
    _size_columns(table)

    total_albums = 0
    total_pictures = 0
    total_videos = 0
    total_bytes = 0
    total_on_disk = 0
    total_archive = 0
    total_derived = 0
    for ys in by_year:
        a = ys.aggregate
        table.add_row(
            ys.year,
            _format_count(ys.album_count),
            _format_count(a.unique_pictures),
            _format_count(a.unique_videos),
            *_size_cells(
                a.total.apparent_bytes,
                a.total.on_disk_bytes,
                a.archive.apparent_bytes,
                a.derived.apparent_bytes,
            ),
        )
        total_albums += ys.album_count
        total_pictures += a.unique_pictures
        total_videos += a.unique_videos
        total_bytes += a.total.apparent_bytes
        total_on_disk += a.total.on_disk_bytes
        total_archive += a.archive.apparent_bytes
        total_derived += a.derived.apparent_bytes

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{_format_count(total_albums)}[/bold]",
        f"[bold]{_format_count(total_pictures)}[/bold]",
        f"[bold]{_format_count(total_videos)}[/bold]",
        *_bold_size_cells(total_bytes, total_on_disk, total_archive, total_derived),
    )

    return table


# ---------------------------------------------------------------------------
# Public formatting functions
# ---------------------------------------------------------------------------


def format_album_stats(stats: AlbumStats) -> Group:
    """Format album-level statistics as a Rich renderable."""
    renderables = _format_aggregate_tables(
        stats.aggregate,
        media_sources=stats.by_media_source,
    )
    renderables.append(Text(""))
    renderables.append(_LEGEND)
    return Group(*renderables)


def format_gallery_stats(stats: GalleryStats) -> Group:
    """Format gallery-level statistics as a Rich renderable."""
    renderables = _format_aggregate_tables(
        stats.aggregate,
        album_count=stats.album_count,
        unique_media_source_names=stats.unique_media_source_names,
    )
    if stats.by_year:
        renderables.append(Text(""))
        renderables.append(_year_table(stats.by_year))
    renderables.append(Text(""))
    renderables.append(_LEGEND)
    return Group(*renderables)
