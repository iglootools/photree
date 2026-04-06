"""Resolve collection import entries against a gallery.

Takes a list of selection entries (IDs, directory names, filenames) and
resolves each to a concrete member (album, collection, image, or video)
by scanning the gallery.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
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

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _looks_like_external_id(entry: str) -> bool:
    """Check if entry looks like an external ID (prefix_base58)."""
    parts = entry.split("_", 1)
    return len(parts) == 2 and parts[0] in _EXTERNAL_PREFIXES


def _looks_like_uuid(entry: str) -> bool:
    """Check if entry looks like a UUID (8-4-4-4-12 hex)."""
    return bool(_UUID_RE.match(entry))


def _parse_external_id_safe(entry: str, prefix: str) -> str | None:
    """Parse an external ID, returning None on failure."""
    try:
        return parse_external_id(entry, prefix)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Gallery scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _GalleryIndex:
    """Lightweight index built by scanning the gallery once."""

    album_ids: frozenset[str]
    album_names: dict[str, tuple[str, ...]]  # dir name → album internal IDs
    collection_ids: frozenset[str]
    collection_names: dict[str, tuple[str, ...]]  # dir name → collection internal IDs
    image_ids: frozenset[str]
    video_ids: frozenset[str]


def _build_gallery_index(gallery_dir: Path) -> _GalleryIndex:
    """Scan the gallery and build a lightweight lookup index."""
    album_ids: set[str] = set()
    album_names: defaultdict[str, list[str]] = defaultdict(list)
    image_ids: set[str] = set()
    video_ids: set[str] = set()

    for album_dir in discover_albums(gallery_dir):
        meta = load_album_metadata(album_dir)
        if meta is not None:
            album_ids.add(meta.id)
            album_names[album_dir.name].append(meta.id)
            media_meta = load_media_metadata(album_dir)
            if media_meta is not None:
                for source in media_meta.media_sources.values():
                    image_ids.update(source.images)
                    video_ids.update(source.videos)

    collection_ids: set[str] = set()
    collection_names: defaultdict[str, list[str]] = defaultdict(list)
    for col_dir in discover_collections(gallery_dir):
        meta = load_collection_metadata(col_dir)
        if meta is not None:
            collection_ids.add(meta.id)
            collection_names[col_dir.name].append(meta.id)

    return _GalleryIndex(
        album_ids=frozenset(album_ids),
        album_names={k: tuple(v) for k, v in album_names.items()},
        collection_ids=frozenset(collection_ids),
        collection_names={k: tuple(v) for k, v in collection_names.items()},
        image_ids=frozenset(image_ids),
        video_ids=frozenset(video_ids),
    )


# ---------------------------------------------------------------------------
# Entry resolution
# ---------------------------------------------------------------------------

# Mapping from external prefix to (member_type, id_prefix, index_field)
_PREFIX_MAP: dict[str, tuple[str, str]] = {
    "album": ("album", ALBUM_ID_PREFIX),
    "collection": ("collection", COLLECTION_ID_PREFIX),
    "image": ("image", IMAGE_ID_PREFIX),
    "video": ("video", VIDEO_ID_PREFIX),
}


def _resolve_external_id(
    entry: str, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Try to resolve as an external ID."""
    prefix = entry.split("_", 1)[0]
    mapping = _PREFIX_MAP.get(prefix)
    if mapping is None:
        return (None, None, ResolutionError(entry, f"unknown ID prefix: {prefix}"))

    member_type, id_prefix = mapping
    internal = _parse_external_id_safe(entry, id_prefix)
    id_pool = {
        "album": index.album_ids,
        "collection": index.collection_ids,
        "image": index.image_ids,
        "video": index.video_ids,
    }[member_type]

    if internal and internal in id_pool:
        return (member_type, internal, None)
    else:
        return (
            None,
            None,
            ResolutionError(entry, f"{member_type} not found in gallery"),
        )


def _resolve_uuid(
    entry: str, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Try to resolve as an internal UUID."""
    # Check pools in priority order
    pools = [
        ("album", index.album_ids),
        ("collection", index.collection_ids),
        ("image", index.image_ids),
        ("video", index.video_ids),
    ]
    for member_type, pool in pools:
        if entry in pool:
            return (member_type, entry, None)
    return (None, None, ResolutionError(entry, "UUID not found in gallery"))


def _resolve_name(
    entry: str, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Try to resolve as a directory name."""
    name_pools = [
        ("album", index.album_names),
        ("collection", index.collection_names),
    ]
    for member_type, names in name_pools:
        if entry in names:
            ids = names[entry]
            match len(ids):
                case 1:
                    return (member_type, ids[0], None)
                case n:
                    return (
                        None,
                        None,
                        ResolutionError(
                            entry, f"ambiguous: matches {n} {member_type}s"
                        ),
                    )
    return (None, None, ResolutionError(entry, "not found in gallery"))


def _resolve_entry(
    entry: str, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Resolve a single entry to (member_type, internal_id, error).

    Returns exactly one of: a resolved member or an error.
    """
    if _looks_like_external_id(entry):
        return _resolve_external_id(entry, index)
    elif _looks_like_uuid(entry):
        return _resolve_uuid(entry, index)
    else:
        return _resolve_name(entry, index)


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

    Uses imperative accumulation because duplicate detection requires
    tracking state (seen_ids) across iterations.
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
        elif internal_id in seen_ids:
            errors.append(
                ResolutionError(
                    entry,
                    f"duplicate: same item already referenced by '{seen_ids[internal_id]}'",
                )
            )
        else:
            assert member_type is not None and internal_id is not None
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
