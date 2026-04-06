"""Resolve collection import entries against a gallery.

Takes a list of selection entries (IDs, directory names, filenames) and
resolves each to a concrete member (album, collection, image, or video)
by scanning the gallery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...album.id import (
    ALBUM_ID_PREFIX,
    IMAGE_ID_PREFIX,
    VIDEO_ID_PREFIX,
    parse_external_id,
)
from ...album.store.album_discovery import discover_albums
from ...album.store.media_metadata import load_media_metadata
from ...album.store.metadata import load_album_metadata
from ...collection.id import COLLECTION_ID_PREFIX
from ...collection.store.collection_discovery import discover_collections
from ...collection.store.metadata import load_collection_metadata


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedMembers:
    """Resolved members from selection entries."""

    albums: tuple[str, ...]
    collections: tuple[str, ...]
    images: tuple[str, ...]
    videos: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionError:
    """A single resolution error."""

    entry: str
    message: str


@dataclass(frozen=True)
class ResolutionResult:
    """Full result of resolving selection entries."""

    members: ResolvedMembers
    errors: tuple[ResolutionError, ...]

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# ID parsing helpers
# ---------------------------------------------------------------------------

_EXTERNAL_PREFIXES = {
    ALBUM_ID_PREFIX,
    COLLECTION_ID_PREFIX,
    IMAGE_ID_PREFIX,
    VIDEO_ID_PREFIX,
}


def _looks_like_external_id(entry: str) -> bool:
    """Check if entry looks like an external ID (prefix_base58)."""
    parts = entry.split("_", 1)
    return len(parts) == 2 and parts[0] in _EXTERNAL_PREFIXES


def _looks_like_uuid(entry: str) -> bool:
    """Check if entry looks like a UUID (8-4-4-4-12 hex)."""
    import re

    return bool(
        re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            entry,
        )
    )


def _parse_external_id_safe(entry: str, prefix: str) -> str | None:
    """Parse an external ID, returning None on failure."""
    try:
        return parse_external_id(entry, prefix)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Gallery scanning
# ---------------------------------------------------------------------------


@dataclass
class _GalleryIndex:
    """Lightweight index built by scanning the gallery once."""

    # album internal ID → True
    album_ids: dict[str, bool] = field(default_factory=dict)
    # album dir name → album internal ID (may have multiple; track for ambiguity)
    album_names: dict[str, list[str]] = field(default_factory=dict)
    # collection internal ID → True
    collection_ids: dict[str, bool] = field(default_factory=dict)
    # collection dir name → collection internal ID
    collection_names: dict[str, list[str]] = field(default_factory=dict)
    # image internal ID → True
    image_ids: dict[str, bool] = field(default_factory=dict)
    # video internal ID → True
    video_ids: dict[str, bool] = field(default_factory=dict)


def _build_gallery_index(gallery_dir: Path) -> _GalleryIndex:
    """Scan the gallery and build a lightweight lookup index."""
    index = _GalleryIndex()

    # Scan albums
    for album_dir in discover_albums(gallery_dir):
        meta = load_album_metadata(album_dir)
        if meta is None:
            continue
        index.album_ids[meta.id] = True
        index.album_names.setdefault(album_dir.name, []).append(meta.id)
        # Scan media metadata
        media_meta = load_media_metadata(album_dir)
        if media_meta is not None:
            for source in media_meta.media_sources.values():
                for img_id in source.images:
                    index.image_ids[img_id] = True
                for vid_id in source.videos:
                    index.video_ids[vid_id] = True

    # Scan collections
    for col_dir in discover_collections(gallery_dir):
        meta = load_collection_metadata(col_dir)
        if meta is None:
            continue
        index.collection_ids[meta.id] = True
        index.collection_names.setdefault(col_dir.name, []).append(meta.id)

    return index


# ---------------------------------------------------------------------------
# Entry resolution
# ---------------------------------------------------------------------------


def _resolve_entry(
    entry: str, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Resolve a single entry to (member_type, internal_id, error).

    Returns exactly one of: a resolved member or an error.
    """
    # 1. Try external ID formats
    if _looks_like_external_id(entry):
        prefix = entry.split("_", 1)[0]
        match prefix:
            case "album":
                internal = _parse_external_id_safe(entry, ALBUM_ID_PREFIX)
                if internal and internal in index.album_ids:
                    return ("album", internal, None)
                return (
                    None,
                    None,
                    ResolutionError(entry, "album not found in gallery"),
                )
            case "collection":
                internal = _parse_external_id_safe(entry, COLLECTION_ID_PREFIX)
                if internal and internal in index.collection_ids:
                    return ("collection", internal, None)
                return (
                    None,
                    None,
                    ResolutionError(entry, "collection not found in gallery"),
                )
            case "image":
                internal = _parse_external_id_safe(entry, IMAGE_ID_PREFIX)
                if internal and internal in index.image_ids:
                    return ("image", internal, None)
                return (
                    None,
                    None,
                    ResolutionError(entry, "image not found in gallery"),
                )
            case "video":
                internal = _parse_external_id_safe(entry, VIDEO_ID_PREFIX)
                if internal and internal in index.video_ids:
                    return ("video", internal, None)
                return (
                    None,
                    None,
                    ResolutionError(entry, "video not found in gallery"),
                )
            case _:
                return (
                    None,
                    None,
                    ResolutionError(entry, f"unknown ID prefix: {prefix}"),
                )

    # 2. Try internal UUID — check all ID pools
    if _looks_like_uuid(entry):
        if entry in index.album_ids:
            return ("album", entry, None)
        if entry in index.collection_ids:
            return ("collection", entry, None)
        if entry in index.image_ids:
            return ("image", entry, None)
        if entry in index.video_ids:
            return ("video", entry, None)
        return (None, None, ResolutionError(entry, "UUID not found in gallery"))

    # 3. Try directory name — albums first, then collections
    if entry in index.album_names:
        ids = index.album_names[entry]
        if len(ids) > 1:
            return (
                None,
                None,
                ResolutionError(entry, f"ambiguous: matches {len(ids)} albums"),
            )
        return ("album", ids[0], None)

    if entry in index.collection_names:
        ids = index.collection_names[entry]
        if len(ids) > 1:
            return (
                None,
                None,
                ResolutionError(entry, f"ambiguous: matches {len(ids)} collections"),
            )
        return ("collection", ids[0], None)

    return (None, None, ResolutionError(entry, "not found in gallery"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_entries(
    entries: tuple[str, ...],
    gallery_dir: Path,
) -> ResolutionResult:
    """Resolve selection entries against the gallery.

    Scans the gallery once to build a lookup index, then resolves each
    entry. Returns resolved members and any errors.
    """
    index = _build_gallery_index(gallery_dir)

    albums: list[str] = []
    collections: list[str] = []
    images: list[str] = []
    videos: list[str] = []
    errors: list[ResolutionError] = []

    seen_ids: dict[str, str] = {}  # internal_id → entry (for duplicate detection)

    for entry in entries:
        member_type, internal_id, error = _resolve_entry(entry, index)
        if error is not None:
            errors.append(error)
            continue
        assert member_type is not None and internal_id is not None

        # Check for duplicates
        if internal_id in seen_ids:
            errors.append(
                ResolutionError(
                    entry,
                    f"duplicate: same item already referenced by '{seen_ids[internal_id]}'",
                )
            )
            continue
        seen_ids[internal_id] = entry

        match member_type:
            case "album":
                albums.append(internal_id)
            case "collection":
                collections.append(internal_id)
            case "image":
                images.append(internal_id)
            case "video":
                videos.append(internal_id)

    return ResolutionResult(
        members=ResolvedMembers(
            albums=tuple(albums),
            collections=tuple(collections),
            images=tuple(images),
            videos=tuple(videos),
        ),
        errors=tuple(errors),
    )
