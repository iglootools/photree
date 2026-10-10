"""Pydantic base model for photree's YAML metadata (kebab-case keys, frozen)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


def _to_kebab(name: str) -> str:
    return name.replace("_", "-")


class PhotreeModel(BaseModel):
    """Base for photree's YAML metadata models: frozen, kebab-case keys."""

    model_config = ConfigDict(
        alias_generator=_to_kebab,
        populate_by_name=True,
        frozen=True,
    )
