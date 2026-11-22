"""
Discover per-media-source import tasks from ``to-import-*`` directories.

An album may carry multiple import staging entries, one per media source:

- ``to-import-ios-<name>/`` (and/or ``to-import-ios-<name>.csv``) — an iOS
  selection list matched by image number against an Image Capture directory.
- ``to-import-std-<name>/`` — a std source whose ``orig/`` and ``edit/`` files
  are imported directly (no selection matching, no Image Capture source).
"""

from dataclasses import dataclass
from pathlib import Path

from photree.album.staging import STAGING_CSV_RE, STAGING_DIR_RE
from photree.album.store.media_source import (
    DEFAULT_MEDIA_SOURCE,
    MediaSource,
    MediaSourceType,
    ios_media_source,
    std_media_source,
)
from photree.common.fs import list_dirs, list_files


@dataclass(frozen=True)
class ImportTask:
    """
    One media source to import.

    iOS tasks carry ``selection_dir`` and/or ``selection_csv`` (a filename
    selection list). Std tasks carry ``staging_dir`` (files imported directly).
    """

    media_source: MediaSource
    selection_dir: Path | None = None  # iOS: to-import-ios-<name>/
    selection_csv: Path | None = None  # iOS: to-import-ios-<name>.csv
    staging_dir: Path | None = None  # std: to-import-std-<name>/

    @property
    def name(self) -> str:
        """Return the name of the media source to import into."""
        return self.media_source.name

    @property
    def is_ios(self) -> bool:
        """Return whether the task imports an iOS media source."""
        return self.media_source.is_ios

    @property
    def is_std(self) -> bool:
        """Return whether the task imports a std media source."""
        return self.media_source.is_std


def _staging_dirs(album_dir: Path, kind: MediaSourceType) -> dict[str, Path]:
    """
    ``{media source name: to-import-<kind>-<name>/}`` in *album_dir*.

    ``list_dirs`` returns ``[]`` for a missing *album_dir*.
    """
    return {
        m.group(2): album_dir / m.group(0)
        for d in list_dirs(album_dir)
        if (m := STAGING_DIR_RE.match(d)) and m.group(1) == kind
    }


def discover_import_tasks(album_dir: Path) -> list[ImportTask]:
    """Return tasks sorted with ``main`` first, then by name, iOS before std."""
    ios_dirs = _staging_dirs(album_dir, MediaSourceType.IOS)
    std_dirs = _staging_dirs(album_dir, MediaSourceType.STD)
    ios_csvs = {
        m.group(1): album_dir / m.group(0)
        for f in list_files(album_dir)
        if (m := STAGING_CSV_RE.match(f))
    }

    tasks = [
        *(
            ImportTask(
                media_source=ios_media_source(name),
                selection_dir=ios_dirs.get(name),
                selection_csv=ios_csvs.get(name),
            )
            for name in set(ios_dirs) | set(ios_csvs)
        ),
        *(
            ImportTask(media_source=std_media_source(name), staging_dir=path)
            for name, path in std_dirs.items()
        ),
    ]
    return sorted(
        tasks,
        key=lambda t: (
            t.name != DEFAULT_MEDIA_SOURCE,
            t.name,
            t.media_source.media_source_type,
        ),
    )


def has_import_tasks(album_dir: Path) -> bool:
    """Return whether *album_dir* holds any ``to-import-*`` dir or iOS CSV."""
    return bool(discover_import_tasks(album_dir))
