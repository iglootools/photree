"""JPEG completeness checks.

Verifies that ``{name}-jpg/`` mirrors ``{name}-img/`` with a JPEG
counterpart for every file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import file_ext, list_files
from ..store.protocol import (
    CONVERT_TO_JPEG_EXTENSIONS,
    COPY_AS_IS_TO_JPEG_EXTENSIONS,
    MediaSource,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JpegCheck:
    """Result of checking main-jpg against main-img."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def success(self) -> bool:
        return not self.missing and not self.extra


@dataclass(frozen=True)
class AlbumJpegIntegrityResult:
    """JPEG integrity check result across all contributors (iOS + std)."""

    by_media_source: tuple[tuple[MediaSource, JpegCheck], ...]

    @property
    def success(self) -> bool:
        return all(check.success for _, check in self.by_media_source)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _expected_jpeg_name(heic_filename: str) -> str | None:
    """Return the expected JPEG filename for a main-img file, or None if not convertible."""
    ext = file_ext(heic_filename)
    match True:
        case _ if ext in CONVERT_TO_JPEG_EXTENSIONS:
            return Path(heic_filename).with_suffix(".jpg").name
        case _ if ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
            return heic_filename
        case _:
            return None


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_jpeg_dir(
    main_img_dir: Path,
    main_jpg_dir: Path,
    *,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> JpegCheck:
    """Check that main-jpg has a counterpart for every file in main-img."""
    heic_files = list_files(main_img_dir)
    jpeg_files = set(list_files(main_jpg_dir))

    expected_jpegs = {
        jpeg_name: f
        for f in heic_files
        if (jpeg_name := _expected_jpeg_name(f)) is not None
    }

    present = [name for name in sorted(expected_jpegs) if name in jpeg_files]
    missing = [name for name in sorted(expected_jpegs) if name not in jpeg_files]
    extra = sorted(jpeg_files - set(expected_jpegs.keys()))

    # Fire callbacks
    if on_file_checked:
        for name in present:
            on_file_checked(name, True)
        for name in missing:
            on_file_checked(name, False)
        for name in extra:
            on_file_checked(name, False)

    return JpegCheck(
        present=tuple(present),
        missing=tuple(missing),
        extra=tuple(extra),
    )


def check_album_jpeg_integrity(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> AlbumJpegIntegrityResult:
    """Check ``{name}-jpg/`` for every media source (iOS + std).

    Only checks media sources that have a ``{name}-img/`` directory.
    """
    return AlbumJpegIntegrityResult(
        by_media_source=tuple(
            (
                ms,
                check_jpeg_dir(album_dir / ms.img_dir, album_dir / ms.jpg_dir),
            )
            for ms in media_sources
            if (album_dir / ms.img_dir).is_dir()
        )
    )
