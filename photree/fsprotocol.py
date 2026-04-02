"""Shared filesystem protocol — foundational types used across domains."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Pydantic base model (kebab-case YAML aliases, frozen)
# ---------------------------------------------------------------------------


def _to_kebab(name: str) -> str:
    return name.replace("_", "-")


class _BaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_kebab,
        populate_by_name=True,
        frozen=True,
    )


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PHOTREE_DIR = ".photree"


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class LinkMode(StrEnum):
    """How main-dir files reference their source."""

    COPY = "copy"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"
