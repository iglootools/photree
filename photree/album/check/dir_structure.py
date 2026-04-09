"""Album directory structure checks.

Verifies that expected subdirectories are present for each media source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..store.protocol import MAIN_MEDIA_SOURCE, MediaSource  # noqa: F401 — re-exported


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


def _is_group_present(album_dir: Path, group: tuple[str, ...]) -> bool:
    """Check if all directories in a group are present."""
    return all((album_dir / d).is_dir() for d in group)


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

    For legacy std sources whose ``std-{name}/`` archive directory does not
    yet exist on disk, archive sub-directories will naturally be reported as
    missing or optional depending on which browsable directories are present.
    """
    if not media_sources:
        # No media sources found — report missing for main media source
        return AlbumDirCheck(
            present=(),
            missing=MAIN_MEDIA_SOURCE.required_subdirs,
        )

    all_present: list[str] = []
    all_missing: list[str] = []
    all_optional_present: list[str] = []
    all_optional_absent: list[str] = []

    for ms in media_sources:
        image_present = _is_group_present(album_dir, ms.image_subdirs)
        video_present = _is_group_present(album_dir, ms.video_subdirs)

        required = [
            *(
                ms.image_subdirs
                if image_present or _has_any(album_dir, ms.image_subdirs)
                else ()
            ),
            *(
                ms.video_subdirs
                if video_present or _has_any(album_dir, ms.video_subdirs)
                else ()
            ),
        ]

        if not required:
            required = list(ms.required_subdirs)

        optional_from_groups = [
            *(
                ms.image_subdirs
                if not image_present and not _has_any(album_dir, ms.image_subdirs)
                else ()
            ),
            *(
                ms.video_subdirs
                if not video_present and not _has_any(album_dir, ms.video_subdirs)
                else ()
            ),
        ]

        all_present.extend(d for d in required if (album_dir / d).is_dir())
        all_missing.extend(d for d in required if not (album_dir / d).is_dir())
        all_optional_present.extend(
            d
            for d in (*ms.optional_subdirs, *optional_from_groups)
            if (album_dir / d).is_dir()
        )
        all_optional_absent.extend(
            d
            for d in (*ms.optional_subdirs, *optional_from_groups)
            if not (album_dir / d).is_dir()
        )

    return AlbumDirCheck(
        present=tuple(all_present),
        missing=tuple(all_missing),
        optional_present=tuple(all_optional_present),
        optional_absent=tuple(all_optional_absent),
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
