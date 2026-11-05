from collections.abc import Mapping
from dataclasses import dataclass

from ..store.protocol import CollectionLifecycle, CollectionMembers, CollectionStrategy


@dataclass(frozen=True)
class CollectionStatsEntry:
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
    total: int
    by_combination: Mapping[
        tuple[CollectionMembers, CollectionLifecycle, CollectionStrategy], int
    ]
    total_album_refs: int
    total_collection_refs: int
    total_image_refs: int
    total_video_refs: int
    collections: tuple[CollectionStatsEntry, ...]
