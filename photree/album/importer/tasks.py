"""Discover per-media-source import tasks from ``to-import-*`` directories.

An album may carry multiple import staging entries, one per media source:

- ``to-import-ios-<name>/`` (and/or ``to-import-ios-<name>.csv``) — an iOS
  selection list matched by image number against an Image Capture directory.
- ``to-import-std-<name>/`` — a std source whose ``orig/`` and ``edit/`` files
  are imported directly (no selection matching, no Image Capture source).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_dirs, list_files
from ..store.protocol import (
    DEFAULT_MEDIA_SOURCE,
    TO_IMPORT_PREFIX,
    MediaSource,
    MediaSourceType,
    ios_media_source,
    std_media_source,
)

_DIR_RE = re.compile(rf"^{re.escape(TO_IMPORT_PREFIX)}(ios|std)-(.+)$")
_CSV_RE = re.compile(rf"^{re.escape(TO_IMPORT_PREFIX)}ios-(.+)\.csv$")


@dataclass(frozen=True)
class ImportTask:
    """A single import task targeting one media source.

    iOS tasks carry ``selection_dir`` and/or ``selection_csv`` (a filename
    selection list). Std tasks carry ``staging_dir`` (files imported directly).
    """

    media_source: MediaSource
    selection_dir: Path | None = None  # iOS: to-import-ios-<name>/
    selection_csv: Path | None = None  # iOS: to-import-ios-<name>.csv
    staging_dir: Path | None = None  # std: to-import-std-<name>/

    @property
    def name(self) -> str:
        return self.media_source.name

    @property
    def is_ios(self) -> bool:
        return self.media_source.is_ios

    @property
    def is_std(self) -> bool:
        return self.media_source.is_std


def _staging_dirs(album_dir: Path, kind: MediaSourceType) -> dict[str, Path]:
    """``{media source name: to-import-<kind>-<name>/}`` in *album_dir*.

    ``list_dirs`` returns ``[]`` for a missing *album_dir*.
    """
    return {
        m.group(2): album_dir / m.group(0)
        for d in list_dirs(album_dir)
        if (m := _DIR_RE.match(d)) and m.group(1) == kind
    }


def discover_import_tasks(album_dir: Path) -> list[ImportTask]:
    """Discover all import tasks in *album_dir*.

    Returns tasks sorted with ``main`` first, then by name, iOS before std.
    """
    ios_dirs = _staging_dirs(album_dir, MediaSourceType.IOS)
    std_dirs = _staging_dirs(album_dir, MediaSourceType.STD)
    ios_csvs = {
        m.group(1): album_dir / m.group(0)
        for f in list_files(album_dir)
        if (m := _CSV_RE.match(f))
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
    """Return True if *album_dir* has at least one ``to-import-*`` entry."""
    return bool(discover_import_tasks(album_dir))
