"""Check for unexpected top-level directories in an album."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_dirs
from ..store.protocol import TO_IMPORT_PREFIX, MediaSource


@dataclass(frozen=True)
class UnexpectedDirsCheck:
    """Result of checking for unexpected top-level directories in an album."""

    unexpected: tuple[str, ...]

    @property
    def success(self) -> bool:
        return len(self.unexpected) == 0


def _is_import_staging_dir(name: str) -> bool:
    """Return True for a ``to-import-{ios,std}-<name>`` staging directory."""
    return name.startswith(f"{TO_IMPORT_PREFIX}ios-") or name.startswith(
        f"{TO_IMPORT_PREFIX}std-"
    )


def check_unexpected_dirs(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> UnexpectedDirsCheck:
    """Check for unexpected top-level directories in *album_dir*.

    Expected directories are ``to-import-{ios,std}-<name>`` staging dirs plus
    all directories belonging to discovered media sources.  Dotdirs (e.g.
    ``.photree/``) are excluded by :func:`list_dirs` and never flagged.
    """
    expected = frozenset(
        subdir.split("/")[0] for ms in media_sources for subdir in ms.all_subdirs
    )
    actual = [d for d in list_dirs(album_dir) if not _is_import_staging_dir(d)]
    return UnexpectedDirsCheck(unexpected=tuple(sorted(set(actual) - expected)))
