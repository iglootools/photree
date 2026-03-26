"""Optimize main directories by replacing copies with links.

Recreates {contributor}-img and {contributor}-vid as hardlinks (default) or
symlinks for each contributor, without touching {contributor}-jpg (HEIC→JPEG
conversions cannot be linked).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import combined as combined_module
from ..fsprotocol import (
    IMG_EXTENSIONS,
    LinkMode,
    MOV_EXTENSIONS,
    discover_contributors,
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
    """Recreate browsable image and video directories as links for all contributors.

    Does NOT touch {contributor}-jpg (HEIC→JPEG conversions cannot be linked).
    """
    total_heic = 0
    total_mov = 0

    for contrib in discover_contributors(album_dir):
        heic_result = combined_module.refresh_main_dir(
            album_dir / contrib.orig_img_dir,
            album_dir / contrib.edit_img_dir,
            album_dir / contrib.img_dir,
            media_extensions=IMG_EXTENSIONS,
            link_mode=link_mode,
            dry_run=dry_run,
            log_cwd=log_cwd,
        )

        mov_result = combined_module.refresh_main_dir(
            album_dir / contrib.orig_vid_dir,
            album_dir / contrib.edit_vid_dir,
            album_dir / contrib.vid_dir,
            media_extensions=MOV_EXTENSIONS,
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
