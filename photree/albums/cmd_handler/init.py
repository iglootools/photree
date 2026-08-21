"""Batch init command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album.id import format_album_external_id, generate_album_id
from ...album.store.metadata import load_album_metadata, save_album_metadata
from ...album.store.protocol import AlbumMetadata
from . import BatchFailure


@dataclass(frozen=True)
class BatchInitResult:
    """Result of batch album initialization."""

    initialized: int
    failures: list[BatchFailure] = field(default_factory=list)

    @property
    def failed_albums(self) -> list[Path]:
        return [f.album_dir for f in self.failures]


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
    failures: list[BatchFailure] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        try:
            metadata = load_album_metadata(album_dir)
            if metadata is not None:
                reason = f"already initialized: {format_album_external_id(metadata.id)}"
                if on_end:
                    on_end(album_name, False, (reason,))
                failures.append(BatchFailure(album_dir=album_dir, reason=reason))
                continue

            if not dry_run:
                generated_id = generate_album_id()
                save_album_metadata(album_dir, AlbumMetadata(id=generated_id))

            if on_end:
                on_end(album_name, True, ())
            initialized += 1
        except Exception as exc:
            if on_end:
                on_end(album_name, False, (str(exc),))
            failures.append(BatchFailure(album_dir=album_dir, reason=str(exc)))

    return BatchInitResult(initialized=initialized, failures=failures)
