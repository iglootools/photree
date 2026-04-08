"""Collection stats data models."""

from __future__ import annotations

from dataclasses import dataclass

from ..store.protocol import CollectionLifecycle, CollectionMembers, CollectionStrategy


@dataclass(frozen=True)
class CollectionStatsEntry:
    """Stats for a single collection."""

    name: str
    members: CollectionMembers
    lifecycle: CollectionLifecycle
    strategy: CollectionStrategy
    album_count: int
    collection_count: int
    image_count: int
    video_count: int


@dataclass(frozen=True)
class GalleryCollectionStats:
    """Aggregate collection stats for a gallery."""

    total: int
    by_combination: dict[
        tuple[CollectionMembers, CollectionLifecycle, CollectionStrategy], int
    ]
    total_album_refs: int
    total_collection_refs: int
    total_image_refs: int
    total_video_refs: int
    collections: tuple[CollectionStatsEntry, ...]
