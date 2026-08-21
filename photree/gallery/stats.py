"""Gallery-level statistics: albums plus the things only a gallery has.

``AlbumsStats`` (in ``album/stats``) covers any set of albums — `albums stats
-d <dir>` produces one for a bare directory with no gallery anywhere. Collection
totals and the gallery face index are meaningful only inside a gallery, so they
live here, wrapped around that type rather than embedded in it.

Keeping them on the album-level model is what made ``album`` import
``collection``, which imports ``album`` back.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Group
from rich.text import Text

from ..album.stats.aggregate import merge_size_stats
from ..album.stats.models import AlbumsStats, SizeStats
from ..album.stats.output import LEGEND, albums_stats_renderables
from ..album.stats.scan import scan_directory_size
from ..collection.stats import compute_gallery_collection_stats
from ..collection.stats.models import GalleryCollectionStats
from ..collection.stats.output import format_collections_overview
from .faces.manifest import gallery_faces_dir


@dataclass(frozen=True)
class GalleryStats:
    """Album statistics plus the gallery-only additions."""

    albums: AlbumsStats
    collection_stats: GalleryCollectionStats | None = None
    # Album caches merged with the gallery-level face index, so the report
    # shows one cache figure rather than two partial ones.
    cache_storage: SizeStats | None = None


def compute_gallery_stats(albums: AlbumsStats, gallery_dir: Path) -> GalleryStats:
    """Wrap *albums* with the collection and cache totals for *gallery_dir*."""
    gallery_face_size = scan_directory_size(gallery_faces_dir(gallery_dir))
    cache_storage = merge_size_stats(
        [s for s in [albums.cache_storage, gallery_face_size] if s.file_count > 0]
    )

    return GalleryStats(
        albums=albums,
        collection_stats=compute_gallery_collection_stats(gallery_dir),
        cache_storage=cache_storage if cache_storage.file_count > 0 else None,
    )


def format_gallery_stats(stats: GalleryStats) -> Group:
    """Format gallery statistics: the albums report plus the collection table."""
    renderables = list(
        albums_stats_renderables(stats.albums, cache_storage=stats.cache_storage)
    )
    if stats.collection_stats is not None and stats.collection_stats.total > 0:
        renderables.append(Text(""))
        renderables.append(format_collections_overview(stats.collection_stats))
    return Group(*renderables, Text(""), LEGEND)
