"""Optimize main directories by replacing copies with links.

Recreates {name}-img and {name}-vid as hardlinks (default) or
symlinks for each media source, without touching {name}-jpg (HEIC→JPEG
conversions cannot be linked).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import combined as combined_module
from ..fsprotocol import (
    IMG_EXTENSIONS,
    LinkMode,
    VID_EXTENSIONS,
    discover_media_sources,
)


@dataclass(frozen=True)
class OptimizeResult:
    """Result of optimizing an album's main directories."""

    heic_count: int
    mov_count: int
    link_mode: LinkMode


def optimize_album(
    album_dir: Path,
    *,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> OptimizeResult:
    """Recreate browsable image and video directories as links for all media sources.

    Does NOT touch {name}-jpg (HEIC→JPEG conversions cannot be linked).
    """
    # Only optimize iOS media sources — plain media sources' browsable dirs
    # are the source of truth and must never be rebuilt.
    ios_sources = [ms for ms in discover_media_sources(album_dir) if ms.is_ios]

    total_heic = 0
    total_mov = 0

    for ms in ios_sources:
        heic_result = combined_module.refresh_main_dir(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            album_dir / ms.img_dir,
            media_extensions=IMG_EXTENSIONS,
            link_mode=link_mode,
            dry_run=dry_run,
            log_cwd=log_cwd,
        )

        mov_result = combined_module.refresh_main_dir(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            album_dir / ms.vid_dir,
            media_extensions=VID_EXTENSIONS,
            link_mode=link_mode,
            dry_run=dry_run,
            log_cwd=log_cwd,
        )

        total_heic += heic_result.copied
        total_mov += mov_result.copied

    return OptimizeResult(
        heic_count=total_heic,
        mov_count=total_mov,
        link_mode=link_mode,
    )
