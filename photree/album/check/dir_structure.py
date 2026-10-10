"""Album directory structure checks.

Verifies that expected subdirectories are present for each media source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..store.media_source import MAIN_MEDIA_SOURCE, MediaSource


@dataclass(frozen=True)
class AlbumDirCheck:
    """Result of checking an album directory for expected subdirectories."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    optional_present: tuple[str, ...] = ()
    optional_absent: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.missing) == 0


def _has_any(album_dir: Path, group: tuple[str, ...]) -> bool:
    """Check if any directory in a group is present."""
    return any((album_dir / d).is_dir() for d in group)


def check_album_dir_structure(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> AlbumDirCheck:
    """Check which expected album subdirectories are present in *album_dir*.

    Iterates over all media sources (iOS and std) and checks each media
    source's directory groups independently.  Results are aggregated.

    Per media source, at least one directory group must be fully present:
    - Image group: ``{archive}/orig-img``, ``{name}-img``, ``{name}-jpg``
    - Video group: ``{archive}/orig-vid``, ``{name}-vid``

    Within present groups, all directories are required.
    Directories from absent groups are reported as optional.
    Optional directories (``edit-img``, ``edit-vid``) are always informational.
    """
    if not media_sources:
        # No media sources found — report missing for main media source
        return AlbumDirCheck(
            present=(),
            missing=MAIN_MEDIA_SOURCE.required_subdirs,
        )
    else:
        per_source = [_check_media_source_dirs(album_dir, ms) for ms in media_sources]
        return AlbumDirCheck(
            present=tuple(d for c in per_source for d in c.present),
            missing=tuple(d for c in per_source for d in c.missing),
            optional_present=tuple(d for c in per_source for d in c.optional_present),
            optional_absent=tuple(d for c in per_source for d in c.optional_absent),
        )


def _check_media_source_dirs(album_dir: Path, ms: MediaSource) -> AlbumDirCheck:
    """Directory check for one media source (see :func:`check_album_dir_structure`)."""
    # A group counts as "in use" as soon as one of its dirs exists; all of
    # its dirs are then required. Unused groups are reported as optional.
    image_used = _has_any(album_dir, ms.image_subdirs)
    video_used = _has_any(album_dir, ms.video_subdirs)
    used_groups = (
        *(ms.image_subdirs if image_used else ()),
        *(ms.video_subdirs if video_used else ()),
    )
    required = used_groups or ms.required_subdirs
    optional = (
        *ms.optional_subdirs,
        *(ms.image_subdirs if not image_used else ()),
        *(ms.video_subdirs if not video_used else ()),
    )
    return AlbumDirCheck(
        present=tuple(d for d in required if (album_dir / d).is_dir()),
        missing=tuple(d for d in required if not (album_dir / d).is_dir()),
        optional_present=tuple(d for d in optional if (album_dir / d).is_dir()),
        optional_absent=tuple(d for d in optional if not (album_dir / d).is_dir()),
    )


def check_album_dir(
    album_dir: Path,
    expected: tuple[str, ...] = MAIN_MEDIA_SOURCE.all_subdirs,
) -> AlbumDirCheck:
    """Check which expected subdirectories are present in *album_dir*.

    Used by import commands to check specific directories (e.g. SELECTION_DIR).
    """
    return AlbumDirCheck(
        present=tuple(d for d in expected if (album_dir / d).is_dir()),
        missing=tuple(d for d in expected if not (album_dir / d).is_dir()),
    )
