"""Resolve collection import entries against a gallery.

Takes a list of selection entries (IDs, directory names, media filenames)
and resolves each to a concrete member (album, collection, image, or video)
by scanning the gallery.

Uses a scan-and-match approach: selection entries are loaded into memory,
then the gallery is scanned once. Each album/collection is checked against
all pending entries. Matches are collected; ambiguous and unresolved
entries are reported as errors.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from itertools import groupby
from operator import itemgetter
from pathlib import Path

from ...album.formats import IMG_EXTENSIONS, VID_EXTENSIONS
from ...album.id import (
    ALBUM_ID_PREFIX,
    IMAGE_ID_PREFIX,
    VIDEO_ID_PREFIX,
    InvalidExternalIdError,
    parse_external_id,
)
from ...album.naming import parse_album_name
from ...album.store.album_discovery import discover_albums
from ...album.store.media_metadata import load_media_metadata
from ...album.store.metadata import load_album_metadata
from ...album.store.protocol import AlbumMetadata
from ...collection.id import COLLECTION_ID_PREFIX
from ...collection.store.collection_discovery import discover_collections
from ...collection.store.metadata import load_collection_metadata
from ...common.fs import file_ext
from ...dates import is_valid_date, timestamp_in_range
from ...foundation.layout import ALBUMS_DIR, COLLECTIONS_DIR
from .selection import SelectionEntry

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class MemberType(StrEnum):
    """Kind of collection member an entry resolved to."""

    ALBUM = "album"
    COLLECTION = "collection"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class ResolvedMembers:
    """Resolved members from selection entries."""

    albums: tuple[str, ...]
    collections: tuple[str, ...]
    images: tuple[str, ...]
    videos: tuple[str, ...]


class ResolutionErrorKind(StrEnum):
    """Why a selection entry could not be resolved."""

    NOT_FOUND = "not-found"
    AMBIGUOUS = "ambiguous"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class ResolutionError:
    """A single resolution error.

    Fields beyond ``entry`` and ``kind`` are only meaningful for some kinds:
    ``match_count``/``unique_count``/``date_hint_missing`` for AMBIGUOUS,
    ``duplicate_of`` (the entry that already claimed the item) for DUPLICATE.
    The human message is rendered by :mod:`.output`.
    """

    entry: str
    kind: ResolutionErrorKind
    match_count: int = 0
    unique_count: int = 0
    date_hint_missing: bool = False
    duplicate_of: str | None = None


@dataclass(frozen=True)
class ResolutionWarning:
    """A non-fatal warning: a media entry's date hint is outside its album date."""

    entry: str
    date_hint: datetime
    album_date: str


@dataclass(frozen=True)
class ResolutionResult:
    """Full result of resolving selection entries."""

    members: ResolvedMembers
    errors: tuple[ResolutionError, ...]
    warnings: tuple[ResolutionWarning, ...] = ()

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


def _looks_like_external_id(entry: str) -> bool:
    parts = entry.split("_", 1)
    return len(parts) == 2 and parts[0] in _EXTERNAL_PREFIXES


def _looks_like_uuid(entry: str) -> bool:
    return bool(_UUID_RE.match(entry))


def _has_media_extension(entry: str) -> bool:
    return file_ext(entry) in _MEDIA_EXTENSIONS


def _parse_external_id_safe(entry: str) -> str | None:
    try:
        return parse_external_id(entry, entry.split("_", 1)[0])
    except InvalidExternalIdError:
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
    image_keys: Mapping[str, str]  # media key → image UUID
    video_keys: Mapping[str, str]  # media key → video UUID


@dataclass(frozen=True)
class ScannedCollection:
    """Data extracted from a single collection during gallery scan."""

    collection_id: str
    dir_name: str


def _scanned_album(album_dir: Path, meta: AlbumMetadata) -> ScannedAlbum:
    parsed = parse_album_name(album_dir.name)
    media_meta = load_media_metadata(album_dir)
    sources = list(media_meta.media_sources.values()) if media_meta else []
    return ScannedAlbum(
        album_id=meta.id,
        dir_name=album_dir.name,
        # An album whose date is not a real date (e.g. 2024-02-30) has no
        # range to compare a date hint against: treat it like an undated one
        # rather than letting timestamp_in_range raise mid-resolution.
        album_date=(
            parsed.date if parsed is not None and is_valid_date(parsed.date) else None
        ),
        image_keys={key: mid for s in sources for mid, key in s.images.items()},
        video_keys={key: mid for s in sources for mid, key in s.videos.items()},
    )


def _scan_albums(gallery_dir: Path) -> Iterator[ScannedAlbum]:
    """Yield album data for each album in the gallery."""
    return (
        _scanned_album(album_dir, meta)
        for album_dir in discover_albums(gallery_dir / ALBUMS_DIR)
        for meta in [load_album_metadata(album_dir)]
        if meta is not None
    )


def _scan_collections(gallery_dir: Path) -> Iterator[ScannedCollection]:
    """Yield collection data for each collection in the gallery."""
    return (
        ScannedCollection(collection_id=meta.id, dir_name=col_dir.name)
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
        for meta in [load_collection_metadata(col_dir)]
        if meta is not None
    )


# ---------------------------------------------------------------------------
# Match tracking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Match:
    member_type: MemberType
    internal_id: str
    album_date: str | None = None  # for date-hint filtering on media matches


@dataclass(frozen=True)
class _MediaRequest:
    media_type: MemberType  # IMAGE or VIDEO
    entry_value: str


@dataclass(frozen=True)
class _PendingLookups:
    """Pre-classified selection entries for efficient matching during scan."""

    # internal UUID → SelectionEntry.value that requested it
    wanted_ids: Mapping[str, str]
    # SelectionEntry.value strings that are directory names
    wanted_names: frozenset[str]
    # media key → the first media entry requesting that key
    wanted_media_keys: Mapping[str, _MediaRequest]


@dataclass(frozen=True)
class _IdRequest:
    internal_id: str
    entry_value: str


@dataclass(frozen=True)
class _NameRequest:
    entry_value: str


@dataclass(frozen=True)
class _KeyRequest:
    key: str
    request: _MediaRequest


type _Request = _IdRequest | _NameRequest | _KeyRequest


def _classify(value: str) -> _Request | None:
    """Classify one entry; ``None`` for an unparseable external ID.

    An unparseable ID is not looked up at all, so it ends up NOT_FOUND.
    """
    match value:
        case _ if _looks_like_external_id(value):
            internal = _parse_external_id_safe(value)
            return _IdRequest(internal, value) if internal is not None else None
        case _ if _looks_like_uuid(value):
            return _IdRequest(value, value)
        case _ if _has_media_extension(value):
            media_type = (
                MemberType.IMAGE
                if file_ext(value) in IMG_EXTENSIONS
                else MemberType.VIDEO
            )
            return _KeyRequest(
                _extract_media_key(value), _MediaRequest(media_type, value)
            )
        case _:
            return _NameRequest(value)


def _prepare_lookups(entries: tuple[SelectionEntry, ...]) -> _PendingLookups:
    """Classify entries into lookup structures for the scan phase."""
    requests = [r for e in entries for r in [_classify(e.value)] if r is not None]
    return _PendingLookups(
        wanted_ids={
            r.internal_id: r.entry_value for r in requests if isinstance(r, _IdRequest)
        },
        wanted_names=frozenset(
            r.entry_value for r in requests if isinstance(r, _NameRequest)
        ),
        # Reversed so that, for a key requested twice, the *first* entry wins.
        wanted_media_keys={
            r.key: r.request for r in reversed(requests) if isinstance(r, _KeyRequest)
        },
    )


type _EntryMatch = tuple[str, _Match]  # (entry value, match)


def _media_requesters(
    key: str, media_id: str, media_type: MemberType, lookups: _PendingLookups
) -> list[str]:
    """Entry values requesting this media item, by ID and/or by filename key."""
    by_key = lookups.wanted_media_keys.get(key)
    return [
        *([lookups.wanted_ids[media_id]] if media_id in lookups.wanted_ids else []),
        *(
            [by_key.entry_value]
            if by_key is not None and by_key.media_type == media_type
            else []
        ),
    ]


def _media_matches(
    album: ScannedAlbum,
    keys: Mapping[str, str],
    media_type: MemberType,
    lookups: _PendingLookups,
) -> list[_EntryMatch]:
    return [
        (value, _Match(media_type, media_id, album_date=album.album_date))
        for key, media_id in keys.items()
        for value in _media_requesters(key, media_id, media_type, lookups)
    ]


def _album_matches(album: ScannedAlbum, lookups: _PendingLookups) -> list[_EntryMatch]:
    """Check a single album against all pending entries."""
    as_album = _Match(MemberType.ALBUM, album.album_id)
    return [
        *(
            [(lookups.wanted_ids[album.album_id], as_album)]
            if album.album_id in lookups.wanted_ids
            else []
        ),
        *(
            [(album.dir_name, as_album)]
            if album.dir_name in lookups.wanted_names
            else []
        ),
        *_media_matches(album, album.image_keys, MemberType.IMAGE, lookups),
        *_media_matches(album, album.video_keys, MemberType.VIDEO, lookups),
    ]


def _collection_matches(
    col: ScannedCollection, lookups: _PendingLookups
) -> list[_EntryMatch]:
    """Check a single collection against all pending entries."""
    as_collection = _Match(MemberType.COLLECTION, col.collection_id)
    return [
        *(
            [(lookups.wanted_ids[col.collection_id], as_collection)]
            if col.collection_id in lookups.wanted_ids
            else []
        ),
        *(
            [(col.dir_name, as_collection)]
            if col.dir_name in lookups.wanted_names
            else []
        ),
    ]


def _group_by_entry(
    entries: tuple[SelectionEntry, ...], pairs: Iterable[_EntryMatch]
) -> dict[str, list[_Match]]:
    """Group matches by entry value; every entry gets a (possibly empty) list."""
    # sorted() is stable, so matches keep their scan order within an entry.
    grouped = {
        value: [m for _, m in group]
        for value, group in groupby(sorted(pairs, key=itemgetter(0)), key=itemgetter(0))
    }
    return {e.value: grouped.get(e.value, []) for e in entries}


# ---------------------------------------------------------------------------
# Result building
# ---------------------------------------------------------------------------


def _check_date_mismatch(entry: SelectionEntry, m: _Match) -> list[ResolutionWarning]:
    """Warn if a single-match media entry's date hint doesn't match the album date."""
    match (entry.date_hint, m.album_date):
        case (datetime() as hint, str() as album_date) if _has_media_extension(
            entry.value
        ) and not timestamp_in_range(hint, album_date):
            return [ResolutionWarning(entry.value, hint, album_date)]
        case _:
            return []


def _filter_by_date_hint(
    entry_matches: list[_Match], date_hint: datetime
) -> list[_Match]:
    """Filter media matches by date hint using album date ranges.

    Uses album_date stored in each _Match (captured during scan),
    avoiding a re-scan.
    """
    return [
        m
        for m in entry_matches
        if m.album_date is not None and timestamp_in_range(date_hint, m.album_date)
    ]


def _resolve_entry(
    entry: SelectionEntry, entry_matches: list[_Match]
) -> _Match | ResolutionError:
    """Resolve one entry to its single match, or the reason it has none."""
    is_media = _has_media_extension(entry.value)
    # Apply date-hint filtering for media filenames with multiple matches
    candidates = (
        _filter_by_date_hint(entry_matches, entry.date_hint)
        if len(entry_matches) > 1 and entry.date_hint is not None and is_media
        else entry_matches
    )
    match candidates:
        case []:
            return ResolutionError(entry.value, ResolutionErrorKind.NOT_FOUND)
        case [single]:
            return single
        case _:
            return ResolutionError(
                entry.value,
                ResolutionErrorKind.AMBIGUOUS,
                match_count=len(candidates),
                unique_count=len({m.internal_id for m in candidates}),
                date_hint_missing=entry.date_hint is None and is_media,
            )


def _flag_duplicates(
    entries: tuple[SelectionEntry, ...],
    outcomes: list[_Match | ResolutionError],
) -> list[_Match | ResolutionError]:
    """Turn every match of an item already claimed by an earlier entry into
    a DUPLICATE error (the first entry keeps the item)."""
    # Reversed so the dict keeps the *first* index per internal ID.
    first_index = {
        o.internal_id: i
        for i, o in reversed(list(enumerate(outcomes)))
        if isinstance(o, _Match)
    }
    return [
        ResolutionError(
            entries[i].value,
            ResolutionErrorKind.DUPLICATE,
            duplicate_of=entries[first_index[o.internal_id]].value,
        )
        if isinstance(o, _Match) and first_index[o.internal_id] != i
        else o
        for i, o in enumerate(outcomes)
    ]


def _members_of(matches: list[_Match], member_type: MemberType) -> tuple[str, ...]:
    return tuple(m.internal_id for m in matches if m.member_type == member_type)


def _build_results(
    entries: tuple[SelectionEntry, ...],
    matches: Mapping[str, list[_Match]],
) -> ResolutionResult:
    """Convert raw matches into a ResolutionResult with error detection."""
    outcomes = _flag_duplicates(
        entries, [_resolve_entry(e, matches[e.value]) for e in entries]
    )
    resolved = [(e, o) for e, o in zip(entries, outcomes) if isinstance(o, _Match)]
    accepted = [m for _, m in resolved]
    return ResolutionResult(
        members=ResolvedMembers(
            albums=_members_of(accepted, MemberType.ALBUM),
            collections=_members_of(accepted, MemberType.COLLECTION),
            images=_members_of(accepted, MemberType.IMAGE),
            videos=_members_of(accepted, MemberType.VIDEO),
        ),
        errors=tuple(o for o in outcomes if isinstance(o, ResolutionError)),
        warnings=tuple(w for e, m in resolved for w in _check_date_mismatch(e, m)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_entries(
    entries: tuple[SelectionEntry, ...],
    gallery_dir: Path,
) -> ResolutionResult:
    """Resolve selection entries against the gallery.

    1. Classify entries into lookup structures
    2. Scan albums and collections, matching against pending entries
    3. Build results with ambiguity and duplicate detection
    """
    lookups = _prepare_lookups(entries)
    pairs = [
        *(
            p
            for album in _scan_albums(gallery_dir)
            for p in _album_matches(album, lookups)
        ),
        *(
            p
            for col in _scan_collections(gallery_dir)
            for p in _collection_matches(col, lookups)
        ),
    ]
    return _build_results(entries, _group_by_entry(entries, pairs))
