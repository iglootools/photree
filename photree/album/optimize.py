"""Optimize main directories by replacing copies with links.

Recreates main-img and main-vid as hardlinks (default) or symlinks,
without touching main-jpg (HEIC→JPEG conversions cannot be linked).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import combined as combined_module
from ..fsprotocol import (
    MAIN_IMG_DIR,
    MAIN_VID_DIR,
    IMG_EXTENSIONS,
    LinkMode,
    MOV_EXTENSIONS,
    ORIG_IMG_DIR,
    ORIG_VID_DIR,
    EDIT_IMG_DIR,
    EDIT_VID_DIR,
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
    """Recreate main-img and main-vid as links.

    Does NOT touch main-jpg (HEIC→JPEG conversions cannot be linked).
    """
    heic_result = combined_module.refresh_main_dir(
        album_dir / ORIG_IMG_DIR,
        album_dir / EDIT_IMG_DIR,
        album_dir / MAIN_IMG_DIR,
        media_extensions=IMG_EXTENSIONS,
        link_mode=link_mode,
        dry_run=dry_run,
        log_cwd=log_cwd,
    )

    mov_result = combined_module.refresh_main_dir(
        album_dir / ORIG_VID_DIR,
        album_dir / EDIT_VID_DIR,
        album_dir / MAIN_VID_DIR,
        media_extensions=MOV_EXTENSIONS,
        link_mode=link_mode,
        dry_run=dry_run,
        log_cwd=log_cwd,
    )

    return OptimizeResult(
        heic_count=heic_result.copied,
        mov_count=mov_result.copied,
        link_mode=link_mode,
    )
