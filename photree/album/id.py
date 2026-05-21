"""Album and media ID generation, formatting, and parsing."""

from __future__ import annotations

import uuid as _uuid

from uuid6 import uuid7

from ..common.base58 import base58_decode, base58_encode

ALBUM_ID_PREFIX = "album"
IMAGE_ID_PREFIX = "image"
VIDEO_ID_PREFIX = "video"


def generate_album_id() -> str:
    """Generate a new UUID v7 string for an album."""
    return str(uuid7())


def generate_media_id() -> str:
    """Generate a new UUID v7 string for a media item (image or video)."""
    return str(uuid7())


def format_external_id(type_prefix: str, internal_id: str) -> str:
    """Convert an internal UUID string to ``prefix_base58`` external form."""
    return f"{type_prefix}_{base58_encode(_uuid.UUID(internal_id).bytes)}"


def parse_external_id(external_id: str, expected_prefix: str) -> str:
    """Convert ``prefix_base58`` external form back to a UUID string."""
    prefix, sep, encoded = external_id.partition("_")
    if not sep or prefix != expected_prefix:
        raise ValueError(f"Expected '{expected_prefix}_...' but got '{external_id}'")
    return str(_uuid.UUID(bytes=base58_decode(encoded)))


def format_album_external_id(internal_id: str) -> str:
    """Convenience wrapper for album external IDs."""
    return format_external_id(ALBUM_ID_PREFIX, internal_id)


def format_image_external_id(internal_id: str) -> str:
    """Convenience wrapper for image external IDs."""
    return format_external_id(IMAGE_ID_PREFIX, internal_id)


def format_video_external_id(internal_id: str) -> str:
    """Convenience wrapper for video external IDs."""
    return format_external_id(VIDEO_ID_PREFIX, internal_id)


def parse_image_external_id(external_id: str) -> str:
    """Parse an image external ID back to a UUID string."""
    return parse_external_id(external_id, IMAGE_ID_PREFIX)


def parse_video_external_id(external_id: str) -> str:
    """Parse a video external ID back to a UUID string."""
    return parse_external_id(external_id, VIDEO_ID_PREFIX)
