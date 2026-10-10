"""Collection initialization — create ``.photree/collection.yaml``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .id import generate_collection_id
from .store.metadata import load_collection_metadata, save_collection_metadata
from .store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)


class CollectionAlreadyInitializedError(Exception):
    """The collection already has metadata; its ID must not be replaced."""

    def __init__(self, collection_dir: Path, existing_id: str) -> None:
        self.collection_dir = collection_dir
        self.existing_id = existing_id
        super().__init__(f"Collection already initialized: {collection_dir}")


def init_collection(
    collection_dir: Path,
    *,
    members: CollectionMembers,
    lifecycle: CollectionLifecycle,
    strategy: CollectionStrategy,
    new_id: Callable[[], str] = generate_collection_id,
) -> CollectionMetadata:
    """Write fresh metadata for *collection_dir* and return it.

    Raises :class:`CollectionAlreadyInitializedError` when metadata exists,
    and :class:`~photree.fsprotocol.InvalidMetadataError` when it exists but
    is corrupt: overwriting either would mint a new ID and orphan every
    reference to the old one.
    """
    existing = load_collection_metadata(collection_dir)
    if existing is not None:
        raise CollectionAlreadyInitializedError(collection_dir, existing.id)
    metadata = CollectionMetadata(
        id=new_id(), members=members, lifecycle=lifecycle, strategy=strategy
    )
    save_collection_metadata(collection_dir, metadata)
    return metadata
