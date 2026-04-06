"""Resolve collection import entries against a gallery.

Takes a list of selection entries (IDs, directory names, media filenames)
and resolves each to a concrete member (album, collection, image, or video)
by scanning the gallery.

Resolution order:
1. External ID (``album_*``, ``collection_*``, ``image_*``, ``video_*``)
2. Internal UUID
3. Media filename (has media extension) — uses key + date_hint
4. Directory name (album or collection)
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
from ...album.naming import _timestamp_in_album_range
from ...album.store.album_discovery import discover_albums
from ...album.store.media_metadata import load_media_metadata
from ...album.store.metadata import load_album_metadata
from ...album.store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS
from ...collection.id import COLLECTION_ID_PREFIX
from ...collection.store.collection_discovery import discover_collections
from ...collection.store.metadata import load_collection_metadata
from ...common.fs import file_ext
from ...fsprotocol import ALBUMS_DIR, COLLECTIONS_DIR
from .selection import SelectionEntry


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

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS


def _looks_like_external_id(entry: str) -> bool:
    """Check if entry looks like an external ID (prefix_base58)."""
    parts = entry.split("_", 1)
    return len(parts) == 2 and parts[0] in _EXTERNAL_PREFIXES


def _looks_like_uuid(entry: str) -> bool:
    """Check if entry looks like a UUID (8-4-4-4-12 hex)."""
    return bool(_UUID_RE.match(entry))


def _has_media_extension(entry: str) -> bool:
    """Check if entry has a recognized media file extension."""
    return file_ext(entry) in _MEDIA_EXTENSIONS


def _parse_external_id_safe(entry: str, prefix: str) -> str | None:
    """Parse an external ID, returning None on failure."""
    try:
        return parse_external_id(entry, prefix)
    except ValueError:
        return None


def _extract_media_key(filename: str) -> str:
    """Extract the matching key from a media filename.

    For IMG_-prefixed files (iOS convention): extract all digits.
    For other files: use the filename stem.
    """
    if filename.upper().startswith("IMG_"):
        return "".join(c for c in filename if c.isdigit())
    else:
        return Path(filename).stem


# ---------------------------------------------------------------------------
# Gallery scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MediaKeyEntry:
    """A media item indexed by its key."""

    album_id: str
    media_id: str
    album_date: str | None


@dataclass(frozen=True)
class _GalleryIndex:
    """Lightweight index built by scanning the gallery once."""

    album_ids: frozenset[str]
    album_names: dict[str, tuple[str, ...]]  # dir name → album internal IDs
    collection_ids: frozenset[str]
    collection_names: dict[str, tuple[str, ...]]  # dir name → collection internal IDs
    image_ids: frozenset[str]
    video_ids: frozenset[str]
    # Media key indexes for filename-based resolution
    image_keys: dict[str, list[_MediaKeyEntry]]  # key → entries
    video_keys: dict[str, list[_MediaKeyEntry]]  # key → entries


def _build_gallery_index(gallery_dir: Path) -> _GalleryIndex:
    """Scan the gallery and build a lightweight lookup index."""
    album_ids: set[str] = set()
    album_names: defaultdict[str, list[str]] = defaultdict(list)
    image_ids: set[str] = set()
    video_ids: set[str] = set()
    image_keys: defaultdict[str, list[_MediaKeyEntry]] = defaultdict(list)
    video_keys: defaultdict[str, list[_MediaKeyEntry]] = defaultdict(list)

    for album_dir in discover_albums(gallery_dir / ALBUMS_DIR):
        meta = load_album_metadata(album_dir)
        if meta is not None:
            album_ids.add(meta.id)
            album_names[album_dir.name].append(meta.id)

            # Parse album date for date-hint filtering
            from ...album.naming import parse_album_name

            parsed = parse_album_name(album_dir.name)
            album_date = parsed.date if parsed is not None else None

            media_meta = load_media_metadata(album_dir)
            if media_meta is not None:
                for source in media_meta.media_sources.values():
                    for mid, key in source.images.items():
                        image_ids.add(mid)
                        image_keys[key].append(
                            _MediaKeyEntry(
                                album_id=meta.id,
                                media_id=mid,
                                album_date=album_date,
                            )
                        )
                    for mid, key in source.videos.items():
                        video_ids.add(mid)
                        video_keys[key].append(
                            _MediaKeyEntry(
                                album_id=meta.id,
                                media_id=mid,
                                album_date=album_date,
                            )
                        )

    collection_ids: set[str] = set()
    collection_names: defaultdict[str, list[str]] = defaultdict(list)
    for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR):
        col_meta = load_collection_metadata(col_dir)
        if col_meta is not None:
            collection_ids.add(col_meta.id)
            collection_names[col_dir.name].append(col_meta.id)

    return _GalleryIndex(
        album_ids=frozenset(album_ids),
        album_names={k: tuple(v) for k, v in album_names.items()},
        collection_ids=frozenset(collection_ids),
        collection_names={k: tuple(v) for k, v in collection_names.items()},
        image_ids=frozenset(image_ids),
        video_ids=frozenset(video_ids),
        image_keys=dict(image_keys),
        video_keys=dict(video_keys),
    )


# ---------------------------------------------------------------------------
# Entry resolution
# ---------------------------------------------------------------------------

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


def _resolve_media_file(
    selection: SelectionEntry, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Resolve a media filename by key extraction + date hint filtering.

    Determines media type from extension, extracts key (image number or
    stem), looks up candidates in the key index, and uses date_hint to
    disambiguate when multiple candidates match.
    """
    ext = file_ext(selection.value)
    if ext in IMG_EXTENSIONS:
        member_type = "image"
        key_index = index.image_keys
    else:
        member_type = "video"
        key_index = index.video_keys

    key = _extract_media_key(selection.value)
    candidates = key_index.get(key, [])

    if not candidates:
        return (
            None,
            None,
            ResolutionError(
                selection.value, f"no {member_type} with key '{key}' found in gallery"
            ),
        )

    # Filter by date hint if available
    if selection.date_hint is not None and len(candidates) > 1:
        candidates = [
            c
            for c in candidates
            if c.album_date is not None
            and _timestamp_in_album_range(selection.date_hint, c.album_date)
        ]

    match len(candidates):
        case 0:
            return (
                None,
                None,
                ResolutionError(
                    selection.value,
                    f"no {member_type} with key '{key}' matches date hint "
                    f"{selection.date_hint}",
                ),
            )
        case 1:
            return (member_type, candidates[0].media_id, None)
        case n:
            album_ids = {c.album_id for c in candidates}
            return (
                None,
                None,
                ResolutionError(
                    selection.value,
                    f"ambiguous: {member_type} key '{key}' matches {n} items "
                    f"across {len(album_ids)} album(s)"
                    + (
                        " — provide a date hint to disambiguate"
                        if selection.date_hint is None
                        else ""
                    ),
                ),
            )


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
    selection: SelectionEntry, index: _GalleryIndex
) -> tuple[str | None, str | None, ResolutionError | None]:
    """Resolve a single entry to (member_type, internal_id, error).

    Returns exactly one of: a resolved member or an error.
    """
    entry = selection.value
    if _looks_like_external_id(entry):
        return _resolve_external_id(entry, index)
    elif _looks_like_uuid(entry):
        return _resolve_uuid(entry, index)
    elif _has_media_extension(entry):
        return _resolve_media_file(selection, index)
    else:
        return _resolve_name(entry, index)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_entries(
    entries: tuple[SelectionEntry, ...],
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

    seen_ids: dict[str, str] = {}  # internal_id → entry value (for duplicate detection)

    for selection in entries:
        member_type, internal_id, error = _resolve_entry(selection, index)
        if error is not None:
            errors.append(error)
        elif internal_id in seen_ids:
            errors.append(
                ResolutionError(
                    selection.value,
                    f"duplicate: same item already referenced by '{seen_ids[internal_id]}'",
                )
            )
        else:
            assert member_type is not None and internal_id is not None
            seen_ids[internal_id] = selection.value
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
