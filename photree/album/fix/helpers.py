"""Shared helpers for fix operations."""

from __future__ import annotations

from pathlib import Path

from ..store.media_source import MediaSource


class MissingArchiveError(FileNotFoundError):
    """A std media source's archive directory is absent.

    Archive-dependent operations (rebuilding or pruning browsable dirs) would
    otherwise run against an incomplete media source. Carries the album and
    archive name; the CLI renders the path with ``display_path``.
    """

    def __init__(self, album_dir: Path, archive_dir: str) -> None:
        self.album_dir = album_dir
        self.archive_dir = archive_dir
        super().__init__(
            f"Archive directory {archive_dir} does not exist in album "
            f"{album_dir.name!r}; archive-dependent fixes cannot run without it."
        )


class NotAnIosMediaSourceError(ValueError):
    """An iOS-only fix was asked to run on a std media source."""

    def __init__(self, media_source: str) -> None:
        self.media_source = media_source
        super().__init__(f"Media source {media_source!r} is not an iOS media source")


def _require_archive(album_dir: Path, ms: MediaSource) -> None:
    """Raise :class:`MissingArchiveError` if the archive directory is absent.

    Archive-dependent operations (rebuilding or pruning browsable dirs)
    require the source's ``{archive}/`` directory; guarding here prevents
    destructive operations from running against an incomplete media source.
    """
    if ms.is_std and not (album_dir / ms.archive_dir).is_dir():
        raise MissingArchiveError(album_dir, ms.archive_dir)


def require_ios(ms: MediaSource) -> None:
    """Raise :class:`NotAnIosMediaSourceError` unless *ms* is an iOS source."""
    if not ms.is_ios:
        raise NotAnIosMediaSourceError(ms.name)
