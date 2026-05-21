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


class CollectionMembers(StrEnum):
    """How members are selected."""

    SMART = "smart"
    MANUAL = "manual"


class CollectionLifecycle(StrEnum):
    """How the collection is managed."""

    IMPLICIT = "implicit"
    EXPLICIT = "explicit"


class CollectionStrategy(StrEnum):
    """Rule for member selection."""

    IMPORT = "import"
    DATE_RANGE = "date-range"
    ALBUM_SERIES = "album-series"
    CHAPTER = "chapter"


# ---------------------------------------------------------------------------
# Valid combination allowlist
# ---------------------------------------------------------------------------

_VALID_COMBINATIONS: set[
    tuple[CollectionMembers, CollectionLifecycle, CollectionStrategy]
] = {
    (CollectionMembers.MANUAL, CollectionLifecycle.EXPLICIT, CollectionStrategy.IMPORT),
    (
        CollectionMembers.SMART,
        CollectionLifecycle.EXPLICIT,
        CollectionStrategy.DATE_RANGE,
    ),
    (CollectionMembers.SMART, CollectionLifecycle.EXPLICIT, CollectionStrategy.CHAPTER),
    (
        CollectionMembers.SMART,
        CollectionLifecycle.IMPLICIT,
        CollectionStrategy.ALBUM_SERIES,
    ),
}


def validate_collection_config(
    members: CollectionMembers,
    lifecycle: CollectionLifecycle,
    strategy: CollectionStrategy,
) -> str | None:
    """Return an error message if the combination is invalid, else None."""
    if (members, lifecycle, strategy) in _VALID_COMBINATIONS:
        return None
    else:
        return (
            f"invalid combination: members={members.value}, "
            f"lifecycle={lifecycle.value}, strategy={strategy.value}. "
            f"See 'photree collection init --help' for valid combinations."
        )


# ---------------------------------------------------------------------------
# Metadata model
# ---------------------------------------------------------------------------


class CollectionMetadata(_BaseModel):
    """Per-collection metadata stored in ``.photree/collection.yaml``."""

    id: str = Field(description="UUID v7 identifying the collection.")
    members: CollectionMembers = Field(description="How members are selected.")
    lifecycle: CollectionLifecycle = Field(description="How the collection is managed.")
    strategy: CollectionStrategy = Field(
        default=CollectionStrategy.IMPORT,
        description="Rule for member selection.",
    )
    albums: list[str] = Field(default_factory=list, description="Album internal UUIDs.")
    collections: list[str] = Field(
        default_factory=list, description="Collection internal UUIDs."
    )
    images: list[str] = Field(default_factory=list, description="Image internal UUIDs.")
    videos: list[str] = Field(default_factory=list, description="Video internal UUIDs.")
