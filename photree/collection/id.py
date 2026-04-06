"""Collection ID generation, formatting, and parsing."""

from __future__ import annotations

from uuid6 import uuid7

from ..album.id import format_external_id, parse_external_id

COLLECTION_ID_PREFIX = "collection"


def generate_collection_id() -> str:
    """Generate a new UUID v7 string for a collection."""
    return str(uuid7())


def format_collection_external_id(internal_id: str) -> str:
    """Convert an internal UUID string to ``collection_base58`` external form."""
    return format_external_id(COLLECTION_ID_PREFIX, internal_id)


def parse_collection_external_id(external_id: str) -> str:
    """Convert ``collection_base58`` external form back to a UUID string."""
    return parse_external_id(external_id, COLLECTION_ID_PREFIX)
