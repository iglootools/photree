"""Collection stats computation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..store.collection_discovery import discover_collections
from ..store.metadata import load_collection_metadata
from ..store.protocol import CollectionLifecycle, CollectionMembers, CollectionStrategy
from ...fsprotocol import COLLECTIONS_DIR
from .models import CollectionStatsEntry, GalleryCollectionStats


def compute_gallery_collection_stats(
    gallery_dir: Path,
) -> GalleryCollectionStats:
    """Compute collection stats for the gallery."""
    entries = [
        CollectionStatsEntry(
            name=col_dir.name,
            members=meta.members,
            lifecycle=meta.lifecycle,
            strategy=meta.strategy,
            album_count=len(meta.albums),
            collection_count=len(meta.collections),
            image_count=len(meta.images),
            video_count=len(meta.videos),
        )
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
        for meta in [load_collection_metadata(col_dir)]
        if meta is not None
    ]

    combination_counts: Counter[
        tuple[CollectionMembers, CollectionLifecycle, CollectionStrategy]
    ] = Counter((e.members, e.lifecycle, e.strategy) for e in entries)

    return GalleryCollectionStats(
        total=len(entries),
        by_combination=dict(combination_counts),
        total_album_refs=sum(e.album_count for e in entries),
        total_collection_refs=sum(e.collection_count for e in entries),
        total_image_refs=sum(e.image_count for e in entries),
        total_video_refs=sum(e.video_count for e in entries),
        collections=tuple(entries),
    )
