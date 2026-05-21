"""Batch post-import check command handler."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...album import check as album_check
from ...common.exif import try_start_exiftool
from ...fsprotocol import resolve_link_mode


def run_batch_post_import_check(
    targets: list[Path],
    *,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> list[Path]:
    """Run post-import checks on imported albums.

    Returns the list of albums that failed checking.
    """
    sips_available = album_check.check_sips_available()
    exiftool = try_start_exiftool()
    check_failed: list[Path] = []
    try:
        for target_dir in targets:
            target_name = display_fn(target_dir)
            if on_start:
                on_start(target_name)
            check_result = album_check.run_album_check(
                target_dir,
                sips_available=sips_available,
                exiftool=exiftool,
                link_mode=resolve_link_mode(None, target_dir),
            )
            if check_result.success:
                if on_end:
                    on_end(target_name, True, ())
            else:
                if on_end:
                    on_end(target_name, False, check_result.error_labels)
                check_failed.append(target_dir)
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)
    return check_failed
