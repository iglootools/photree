"""Collection protocol — models, constants, and enums."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from ...fsprotocol import _BaseModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_YAML = "collection.yaml"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CollectionKind(StrEnum):
    """How members are determined."""

    SMART = "smart"
    MANUAL = "manual"


class CollectionLifecycle(StrEnum):
    """How the collection is managed."""

    IMPLICIT = "implicit"
    EXPLICIT = "explicit"


# ---------------------------------------------------------------------------
# Metadata model
# ---------------------------------------------------------------------------


def validate_kind_lifecycle(
    kind: CollectionKind, lifecycle: CollectionLifecycle
) -> str | None:
    """Return an error message if the kind + lifecycle combination is invalid.

    Returns ``None`` when the combination is valid.
    """
    if lifecycle == CollectionLifecycle.IMPLICIT and kind != CollectionKind.SMART:
        return (
            "implicit collections must be kind=smart (implicit + manual is not allowed)"
        )
    else:
        return None


class CollectionMetadata(_BaseModel):
    """Per-collection metadata stored in ``.photree/collection.yaml``."""

    id: str = Field(description="UUID v7 identifying the collection.")
    kind: CollectionKind = Field(description="How members are determined.")
    lifecycle: CollectionLifecycle = Field(description="How the collection is managed.")
    albums: list[str] = Field(default_factory=list, description="Album internal UUIDs.")
    collections: list[str] = Field(
        default_factory=list, description="Collection internal UUIDs."
    )
    images: list[str] = Field(default_factory=list, description="Image internal UUIDs.")
    videos: list[str] = Field(default_factory=list, description="Video internal UUIDs.")
