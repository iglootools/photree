"""Collection stats output formatting."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..store.protocol import CollectionLifecycle, CollectionMembers, CollectionStrategy
from .models import GalleryCollectionStats

_TABLE_BOX = None  # borderless


def _format_count(n: int) -> str:
    return f"{n:,}"


def _combination_label(
    members: CollectionMembers,
    lifecycle: CollectionLifecycle,
    strategy: CollectionStrategy,
) -> str:
    return f"{members.value} / {lifecycle.value} / {strategy.value}"


def format_collections_overview(stats: GalleryCollectionStats) -> Panel:
    """Format collection overview as a Rich Panel."""
    lines = [f"Collections: {_format_count(stats.total)}"]

    for (members, lifecycle, strategy), count in sorted(
        stats.by_combination.items(),
        key=lambda kv: -kv[1],
    ):
        label = _combination_label(members, lifecycle, strategy)
        lines.append(f"  {label}: {_format_count(count)}")

    lines.append("")
    lines.append(f"Album refs: {_format_count(stats.total_album_refs)}")
    lines.append(f"Collection refs: {_format_count(stats.total_collection_refs)}")
    lines.append(f"Image refs: {_format_count(stats.total_image_refs)}")
    lines.append(f"Video refs: {_format_count(stats.total_video_refs)}")

    return Panel(
        Text("\n".join(lines)),
        title="Collections",
        expand=False,
    )


def format_collections_table(stats: GalleryCollectionStats) -> Table:
    """Per-collection summary table."""
    table = Table(title="Collections", box=_TABLE_BOX)
    table.add_column("Name")
    table.add_column("Members")
    table.add_column("Strategy")
    table.add_column("Albums", justify="right")
    table.add_column("Collections", justify="right")
    table.add_column("Images", justify="right")
    table.add_column("Videos", justify="right")

    for col in stats.collections:
        table.add_row(
            col.name,
            col.members.value,
            col.strategy.value,
            _format_count(col.album_count),
            _format_count(col.collection_count),
            _format_count(col.image_count),
            _format_count(col.video_count),
        )

    return table
