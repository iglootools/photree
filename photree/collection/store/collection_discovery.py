from pathlib import Path

from photree.collection.store.protocol import COLLECTION_YAML
from photree.common.fs import matching_subdirectories
from photree.foundation.layout import PHOTREE_DIR


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
