"""Collection metadata I/O."""

from __future__ import annotations

from pathlib import Path

import yaml

from ...fsprotocol import PHOTREE_DIR
from .protocol import COLLECTION_YAML, CollectionMetadata


def load_collection_metadata(collection_dir: Path) -> CollectionMetadata | None:
    """Read ``.photree/collection.yaml``, or ``None`` if missing."""
    path = collection_dir / PHOTREE_DIR / COLLECTION_YAML
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return CollectionMetadata.model_validate(raw) if isinstance(raw, dict) else None


def save_collection_metadata(
    collection_dir: Path, metadata: CollectionMetadata
) -> None:
    """Write :class:`CollectionMetadata` to ``.photree/collection.yaml``."""
    photree_dir = collection_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    path = photree_dir / COLLECTION_YAML
    path.write_text(
        yaml.safe_dump(
            metadata.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )
