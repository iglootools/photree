"""Batch init command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album.store.metadata import load_album_metadata, save_album_metadata
from ...album.store.protocol import (
    AlbumMetadata,
    format_album_external_id,
    generate_album_id,
)


@dataclass(frozen=True)
class BatchInitResult:
    """Result of batch album initialization."""

    initialized: int
    failed_albums: list[Path] = field(default_factory=list)


def batch_init(
    albums: list[Path],
    *,
    dry_run: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> BatchInitResult:
    """Initialize album metadata for multiple albums.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.
    """
    initialized = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        try:
            metadata = load_album_metadata(album_dir)
            if metadata is not None:
                if on_end:
                    on_end(
                        album_name,
                        False,
                        (
                            f"already initialized: {format_album_external_id(metadata.id)}",
                        ),
                    )
                failed_albums.append(album_dir)
                continue

            if not dry_run:
                generated_id = generate_album_id()
                save_album_metadata(album_dir, AlbumMetadata(id=generated_id))

            if on_end:
                on_end(album_name, True, ())
            initialized += 1
        except Exception:
            if on_end:
                on_end(album_name, False, ())
            failed_albums.append(album_dir)

    return BatchInitResult(initialized=initialized, failed_albums=failed_albums)
