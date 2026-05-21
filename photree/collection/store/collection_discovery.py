"""Collection discovery — find collection directories by scanning for metadata."""

from __future__ import annotations

from pathlib import Path

from ...common.fs import matching_subdirectories
from ...fsprotocol import PHOTREE_DIR
from .protocol import COLLECTION_YAML


def is_collection(directory: Path) -> bool:
    """Check if a directory is a photree collection.

    A directory is a collection if it contains ``.photree/collection.yaml``.
    """
    return (directory / PHOTREE_DIR / COLLECTION_YAML).is_file()


def discover_collections(base_dir: Path) -> list[Path]:
    """Recursively discover collection directories under *base_dir*.

    The *base_dir* itself is never returned as a collection.
    """
    return matching_subdirectories(base_dir, is_collection)
