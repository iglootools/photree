"""Check for unexpected top-level directories in an album."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_dirs
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import SELECTION_DIR


@dataclass(frozen=True)
class UnexpectedDirsCheck:
    """Result of checking for unexpected top-level directories in an album."""

    unexpected: tuple[str, ...]

    @property
    def success(self) -> bool:
        return len(self.unexpected) == 0


def check_unexpected_dirs(album_dir: Path) -> UnexpectedDirsCheck:
    """Check for unexpected top-level directories in *album_dir*.

    Expected directories are ``to-import/`` plus all directories belonging
    to discovered media sources.  Dotdirs (e.g. ``.photree/``) are excluded
    by :func:`list_dirs` and never flagged.
    """
    media_sources = discover_media_sources(album_dir)
    expected = frozenset(
        {
            SELECTION_DIR,
            *(
                subdir.split("/")[0]
                for ms in media_sources
                for subdir in ms.all_subdirs
            ),
        }
    )
    actual = list_dirs(album_dir)
    return UnexpectedDirsCheck(unexpected=tuple(sorted(set(actual) - expected)))
