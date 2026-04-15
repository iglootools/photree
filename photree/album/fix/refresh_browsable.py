"""refresh-browsable fix operation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...fsprotocol import LinkMode
from .. import browsable as browsable_module
from .. import jpeg
from ..browsable import RefreshBrowsableDirResult
from ..jpeg import RefreshResult, convert_single_file
from ..live_photo import augment_browsable_img_with_live_photo_videos
from ..store.protocol import (
    IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    VID_EXTENSIONS,
    MediaSource,
)
from .helpers import _delete_dir, _require_archive


@dataclass(frozen=True)
class RefreshBrowsableResult:
    """Result of refreshing all browsable directories for a media source."""

    heic: RefreshBrowsableDirResult
    mov: RefreshBrowsableDirResult
    jpeg: RefreshResult | None


def refresh_browsable(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    convert_file: Callable[..., Path | None] = convert_single_file,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    max_workers: int | None = None,
) -> RefreshBrowsableResult:
    """Delete browsable dirs, rebuild img/vid from archive, then jpeg.

    Works for both iOS and std media sources. Raises
    :class:`FileNotFoundError` for legacy std sources without archives.

    Stage callbacks fire for: ``delete``, ``refresh-heic``, ``refresh-mov``,
    ``refresh-jpeg``.
    """
    _require_archive(album_dir, ms)

    browsable_img = album_dir / ms.img_dir
    browsable_vid = album_dir / ms.vid_dir
    browsable_jpg = album_dir / ms.jpg_dir

    # Delete all browsable directories
    if on_stage_start:
        on_stage_start("delete")
    for d in (browsable_img, browsable_vid, browsable_jpg):
        _delete_dir(d, dry_run=dry_run)
    if on_stage_end:
        on_stage_end("delete")

    # Rebuild browsable img
    if on_stage_start:
        on_stage_start("refresh-heic")
    heic_result = browsable_module.refresh_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        browsable_img,
        media_extensions=IMG_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    # Augment with Live Photo companion videos (iOS only)
    if ms.is_ios:
        augment_browsable_img_with_live_photo_videos(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            browsable_img,
            vid_extensions=IOS_VID_EXTENSIONS,
            key_fn=ms.key_fn,
            link_mode=link_mode,
            dry_run=dry_run,
        )
    if on_stage_end:
        on_stage_end("refresh-heic")

    # Rebuild browsable vid
    if on_stage_start:
        on_stage_start("refresh-mov")
    mov_result = browsable_module.refresh_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        browsable_vid,
        media_extensions=VID_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    if on_stage_end:
        on_stage_end("refresh-mov")

    # Rebuild browsable jpg if browsable img was created
    has_img = browsable_img.is_dir() if not dry_run else heic_result.copied > 0
    if on_stage_start:
        on_stage_start("refresh-jpeg")
    jpeg_result = (
        jpeg.refresh_jpeg_dir(
            browsable_img,
            browsable_jpg,
            dry_run=dry_run,
            convert_file=convert_file,
            max_workers=max_workers,
        )
        if has_img
        else None
    )
    if on_stage_end:
        on_stage_end("refresh-jpeg")

    return RefreshBrowsableResult(heic=heic_result, mov=mov_result, jpeg=jpeg_result)
