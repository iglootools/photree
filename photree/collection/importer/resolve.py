"""Resolve collection import entries against a gallery.

Takes a list of selection entries (IDs, directory names, media filenames)
and resolves each to a concrete member (album, collection, image, or video)
by scanning the gallery.

Uses a scan-and-match approach: selection entries are loaded into memory,
then the gallery is scanned once. Each album/collection is checked against
all pending entries. Matches are accumulated; ambiguous and unresolved
entries are reported as errors.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ...album.id import (
    ALBUM_ID_PREFIX,
    IMAGE_ID_PREFIX,
    VIDEO_ID_PREFIX,
    parse_external_id,
)
from ...album.naming import _timestamp_in_album_range, parse_album_name
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
# Entry classification helpers
# ---------------------------------------------------------------------------

_EXTERNAL_PREFIXES = {
    ALBUM_ID_PREFIX,
    COLLECTION_ID_PREFIX,
    IMAGE_ID_PREFIX,
    VIDEO_ID_PREFIX,
}

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS

_PREFIX_MAP: dict[str, tuple[str, str]] = {
    "album": ("album", ALBUM_ID_PREFIX),
    "collection": ("collection", COLLECTION_ID_PREFIX),
    "image": ("image", IMAGE_ID_PREFIX),
    "video": ("video", VIDEO_ID_PREFIX),
}


def _looks_like_external_id(entry: str) -> bool:
    parts = entry.split("_", 1)
    return len(parts) == 2 and parts[0] in _EXTERNAL_PREFIXES


def _looks_like_uuid(entry: str) -> bool:
    return bool(_UUID_RE.match(entry))


def _has_media_extension(entry: str) -> bool:
    return file_ext(entry) in _MEDIA_EXTENSIONS


def _parse_external_id_safe(entry: str, prefix: str) -> str | None:
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
# Per-item scan data — abstracts album/collection on-disk details
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScannedAlbum:
    """Data extracted from a single album during gallery scan."""

    album_id: str
    dir_name: str
    album_date: str | None
    image_keys: dict[str, str]  # media key → image UUID
    video_keys: dict[str, str]  # media key → video UUID


@dataclass(frozen=True)
class ScannedCollection:
    """Data extracted from a single collection during gallery scan."""

    collection_id: str
    dir_name: str


def _scan_albums(gallery_dir: Path) -> Iterator[ScannedAlbum]:
    """Yield album data for each album in the gallery."""
    for album_dir in discover_albums(gallery_dir / ALBUMS_DIR):
        meta = load_album_metadata(album_dir)
        if meta is None:
            continue

        parsed = parse_album_name(album_dir.name)
        album_date = parsed.date if parsed is not None else None

        image_keys: dict[str, str] = {}
        video_keys: dict[str, str] = {}
        media_meta = load_media_metadata(album_dir)
        if media_meta is not None:
            for source in media_meta.media_sources.values():
                # Invert uuid→key to key→uuid
                for mid, key in source.images.items():
                    image_keys[key] = mid
                for mid, key in source.videos.items():
                    video_keys[key] = mid

        yield ScannedAlbum(
            album_id=meta.id,
            dir_name=album_dir.name,
            album_date=album_date,
            image_keys=image_keys,
            video_keys=video_keys,
        )


def _scan_collections(gallery_dir: Path) -> Iterator[ScannedCollection]:
    """Yield collection data for each collection in the gallery."""
    for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR):
        meta = load_collection_metadata(col_dir)
        if meta is not None:
            yield ScannedCollection(
                collection_id=meta.id,
                dir_name=col_dir.name,
            )


# ---------------------------------------------------------------------------
# Match: a resolved (member_type, internal_id) for a selection entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Match:
    member_type: str  # "album", "collection", "image", "video"
    internal_id: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_entries(
    entries: tuple[SelectionEntry, ...],
    gallery_dir: Path,
) -> ResolutionResult:
    """Resolve selection entries against the gallery.

    Loads entries into memory, scans the gallery once, and matches each
    album/collection against pending entries. Reports ambiguous (multiple
    matches) and unresolved entries as errors.
    """
    # Accumulate all matches per entry value (to detect ambiguity)
    matches: dict[str, list[_Match]] = {e.value: [] for e in entries}
    entry_by_value: dict[str, SelectionEntry] = {e.value: e for e in entries}

    # Classify entries for efficient matching
    external_ids = {e.value for e in entries if _looks_like_external_id(e.value)}
    uuids = {e.value for e in entries if _looks_like_uuid(e.value)}
    media_filenames = {e.value for e in entries if _has_media_extension(e.value)}
    dir_names = {
        e.value
        for e in entries
        if not _looks_like_external_id(e.value)
        and not _looks_like_uuid(e.value)
        and not _has_media_extension(e.value)
    }

    # Pre-resolve external IDs to internal UUIDs
    # (these don't need gallery scan — just parse the base58)
    resolved_external: dict[str, tuple[str, str]] = {}  # value → (type, internal)
    for ext_id in external_ids:
        prefix = ext_id.split("_", 1)[0]
        mapping = _PREFIX_MAP.get(prefix)
        if mapping is not None:
            member_type, id_prefix = mapping
            internal = _parse_external_id_safe(ext_id, id_prefix)
            if internal is not None:
                resolved_external[ext_id] = (member_type, internal)

    # Collect all internal IDs we're looking for (UUIDs + parsed external IDs)
    wanted_ids: dict[str, str] = {}  # internal_id → entry value
    for ext_value, (_, internal) in resolved_external.items():
        wanted_ids[internal] = ext_value
    for uuid_value in uuids:
        wanted_ids[uuid_value] = uuid_value

    # Pre-compute media keys for media filename entries
    media_keys: dict[str, tuple[str, SelectionEntry]] = {}  # key → (media_type, entry)
    for fname in media_filenames:
        ext = file_ext(fname)
        media_type = "image" if ext in IMG_EXTENSIONS else "video"
        key = _extract_media_key(fname)
        media_keys.setdefault(key, (media_type, entry_by_value[fname]))

    # --- Scan albums ---
    for album in _scan_albums(gallery_dir):
        # Match by ID (album ID)
        if album.album_id in wanted_ids:
            entry_value = wanted_ids[album.album_id]
            matches[entry_value].append(_Match("album", album.album_id))

        # Match by dir name
        if album.dir_name in dir_names:
            matches[album.dir_name].append(_Match("album", album.album_id))

        # Match media by image key
        for key, img_uuid in album.image_keys.items():
            if img_uuid in wanted_ids:
                entry_value = wanted_ids[img_uuid]
                matches[entry_value].append(_Match("image", img_uuid))
            if key in media_keys:
                media_type, sel_entry = media_keys[key]
                if media_type == "image":
                    matches[sel_entry.value].append(_Match("image", img_uuid))

        # Match media by video key
        for key, vid_uuid in album.video_keys.items():
            if vid_uuid in wanted_ids:
                entry_value = wanted_ids[vid_uuid]
                matches[entry_value].append(_Match("video", vid_uuid))
            if key in media_keys:
                media_type, sel_entry = media_keys[key]
                if media_type == "video":
                    matches[sel_entry.value].append(_Match("video", vid_uuid))

    # --- Scan collections ---
    for col in _scan_collections(gallery_dir):
        if col.collection_id in wanted_ids:
            entry_value = wanted_ids[col.collection_id]
            matches[entry_value].append(_Match("collection", col.collection_id))

        if col.dir_name in dir_names:
            matches[col.dir_name].append(_Match("collection", col.collection_id))

    # --- Build results ---
    albums: list[str] = []
    collections: list[str] = []
    images: list[str] = []
    videos: list[str] = []
    errors: list[ResolutionError] = []
    seen_ids: dict[str, str] = {}  # internal_id → entry value (duplicate detection)

    for entry in entries:
        entry_matches = matches[entry.value]

        # Apply date-hint filtering for media filenames with multiple matches
        if (
            len(entry_matches) > 1
            and entry.date_hint is not None
            and _has_media_extension(entry.value)
        ):
            # Find the album date for each match via the scanned data
            # Re-scan is avoided because we filter using the match's album context
            # For media matches, filter by album date overlap
            entry_matches = _filter_by_date_hint(entry_matches, entry, gallery_dir)

        match len(entry_matches):
            case 0:
                errors.append(ResolutionError(entry.value, "not found in gallery"))
            case 1:
                m = entry_matches[0]
                if m.internal_id in seen_ids:
                    errors.append(
                        ResolutionError(
                            entry.value,
                            f"duplicate: same item already referenced by "
                            f"'{seen_ids[m.internal_id]}'",
                        )
                    )
                else:
                    seen_ids[m.internal_id] = entry.value
                    match m.member_type:
                        case "album":
                            albums.append(m.internal_id)
                        case "collection":
                            collections.append(m.internal_id)
                        case "image":
                            images.append(m.internal_id)
                        case "video":
                            videos.append(m.internal_id)
            case n:
                unique_ids = {m.internal_id for m in entry_matches}
                errors.append(
                    ResolutionError(
                        entry.value,
                        f"ambiguous: matches {n} items ({len(unique_ids)} unique)"
                        + (
                            " — provide a date hint to disambiguate"
                            if entry.date_hint is None
                            and _has_media_extension(entry.value)
                            else ""
                        ),
                    )
                )

    return ResolutionResult(
        members=ResolvedMembers(
            albums=tuple(albums),
            collections=tuple(collections),
            images=tuple(images),
            videos=tuple(videos),
        ),
        errors=tuple(errors),
    )


def _filter_by_date_hint(
    entry_matches: list[_Match],
    entry: SelectionEntry,
    gallery_dir: Path,
) -> list[_Match]:
    """Filter media matches by date hint using album date ranges.

    Requires a second pass over album metadata for date information.
    Only called when there are multiple matches and a date hint is available.
    """
    assert entry.date_hint is not None

    # Build album_id → date lookup from matched albums
    album_ids_needed = {m.internal_id for m in entry_matches}
    # We need the album that contains each media item — the match's internal_id
    # is the media UUID, not the album ID. We need to re-derive the album context.
    # Since this is rare (only for ambiguous media), a targeted scan is acceptable.
    media_to_album_date: dict[str, str | None] = {}
    for album in _scan_albums(gallery_dir):
        for img_uuid in album.image_keys.values():
            if img_uuid in album_ids_needed:
                media_to_album_date[img_uuid] = album.album_date
        for vid_uuid in album.video_keys.values():
            if vid_uuid in album_ids_needed:
                media_to_album_date[vid_uuid] = album.album_date

    return [
        m
        for m in entry_matches
        if media_to_album_date.get(m.internal_id) is not None
        and _timestamp_in_album_range(
            entry.date_hint,
            media_to_album_date[m.internal_id],  # type: ignore[arg-type]
        )
    ]
