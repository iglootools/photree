"""Check for album directories that belong to no media source."""

from dataclasses import dataclass
from pathlib import Path

from photree.album.staging import is_import_staging_dir
from photree.album.store.media_source import MediaSource
from photree.common.fs import list_dirs


@dataclass(frozen=True)
class UnexpectedDirsCheck:
    """The album directories that belong to no media source."""

    unexpected: tuple[str, ...]

    @property
    def success(self) -> bool:
        """Return whether the album has no unexpected directory."""
        return len(self.unexpected) == 0


def check_unexpected_dirs(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> UnexpectedDirsCheck:
    """
    Find directories in the album that belong to no media source.

    Expected directories are ``to-import-{ios,std}-<name>`` staging dirs plus
    all directories belonging to discovered media sources.  Dotdirs (e.g.
    ``.photree/``) are excluded by :func:`list_dirs` and never flagged.
    """
    expected = frozenset(
        subdir.split("/")[0] for ms in media_sources for subdir in ms.all_subdirs
    )
    actual = [d for d in list_dirs(album_dir) if not is_import_staging_dir(d)]
    return UnexpectedDirsCheck(unexpected=tuple(sorted(set(actual) - expected)))
