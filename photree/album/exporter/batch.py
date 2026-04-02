"""Batch export across multiple album directories."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ...fsprotocol import LinkMode
from ..exporter.protocol import AlbumShareLayout, ShareDirectoryLayout
from ..store.album_discovery import discover_albums as discover_photree_albums
from .single import compute_target_dir, export_album


@dataclass
class BatchExportResult:
    """Result of a batch export run.

    Not frozen because it is incrementally built during the export loop.
    """

    exported: int = 0
    failed: list[tuple[Path, str]] = field(default_factory=list)


def discover_albums(base_dir: Path) -> list[Path]:
    """Discover all album directories under *base_dir*.

    Returns photree albums (recursively, via ``fs.discover_albums``) plus
    immediate subdirectories that are not already covered — i.e. plain
    directories without ``.photree/album.yaml`` that can be exported as-is.
    """
    photree_albums = set(discover_photree_albums(base_dir))
    # Parents of photree albums should not be treated as plain directories
    photree_parents = {a.parent for a in photree_albums}

    other_dirs = sorted(
        p
        for p in base_dir.iterdir()
        if p.is_dir() and p not in photree_albums and p not in photree_parents
    )

    return sorted([*photree_albums, *other_dirs])


def run_batch_export(
    *,
    base_dir: Path | None = None,
    album_dirs: Sequence[Path] | None = None,
    share_dir: Path,
    share_layout: ShareDirectoryLayout = ShareDirectoryLayout.FLAT,
    album_layout: AlbumShareLayout = AlbumShareLayout.MAIN_JPG,
    link_mode: LinkMode = LinkMode.HARDLINK,
    on_exporting: Callable[[str], None] | None = None,
    on_exported: Callable[[str], None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
) -> BatchExportResult:
    """Export multiple albums to *share_dir*.

    Provide exactly one of *base_dir* (discover albums) or *album_dirs*
    (explicit list).

    Callbacks are optional hooks for the CLI layer:
    - ``on_exporting(album_name)`` — called before exporting
    - ``on_exported(album_name)`` — called after success
    - ``on_error(album_name, message)`` — called on failure
    """
    if (base_dir is None) == (album_dirs is None):
        msg = "Exactly one of base_dir or album_dirs must be provided"
        raise ValueError(msg)

    albums = (
        discover_albums(base_dir) if base_dir is not None else list(album_dirs)  # type: ignore[arg-type]
    )
    result = BatchExportResult()

    for album_dir in albums:
        album_name = album_dir.name
        if on_exporting:
            on_exporting(album_name)
        try:
            target_dir = compute_target_dir(share_dir, album_name, share_layout)
            export_album(
                album_dir, target_dir, album_layout=album_layout, link_mode=link_mode
            )
            result.exported += 1
            if on_exported:
                on_exported(album_name)
        except Exception as exc:
            result.failed.append((album_dir, str(exc)))
            if on_error:
                on_error(album_name, str(exc))

    return result
