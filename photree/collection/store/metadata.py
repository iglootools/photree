"""Collection metadata I/O."""

from __future__ import annotations

from pathlib import Path

from ...fsprotocol import PHOTREE_DIR, load_yaml_mapping, validate_metadata, write_yaml
from .protocol import COLLECTION_YAML, CollectionMetadata


def load_collection_metadata(collection_dir: Path) -> CollectionMetadata | None:
    """Read ``.photree/collection.yaml``, or ``None`` if missing.

    Raises :class:`~photree.fsprotocol.InvalidMetadataError` when the file
    exists but is unreadable: treating a corrupt file as absent would let
    ``collection init`` mint a new ID and orphan every reference to the old one.
    """
    path = collection_dir / PHOTREE_DIR / COLLECTION_YAML
    raw = load_yaml_mapping(path)
    return validate_metadata(path, CollectionMetadata, raw) if raw is not None else None


def save_collection_metadata(
    collection_dir: Path, metadata: CollectionMetadata
) -> None:
    """Write :class:`CollectionMetadata` to ``.photree/collection.yaml``."""
    photree_dir = collection_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    write_yaml(
        photree_dir / COLLECTION_YAML,
        metadata.model_dump(by_alias=True, mode="json"),
    )
