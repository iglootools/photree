"""Check that each image in a browsable img dir has its JPEG counterpart."""

from dataclasses import dataclass
from pathlib import Path

from photree.album.formats import (
    CONVERT_TO_JPEG_EXTENSIONS,
    COPY_AS_IS_TO_JPEG_EXTENSIONS,
)
from photree.album.store.media_source import MediaSource
from photree.common.fs import file_ext, list_files
from photree.common.progress import FileEnd


@dataclass(frozen=True)
class JpegCheck:
    """The expected JPEG files found present or missing, and the extra ones."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def success(self) -> bool:
        """Return whether no JPEG is missing or extra."""
        return not self.missing and not self.extra


@dataclass(frozen=True)
class AlbumJpegIntegrityResult:
    """The JPEG check of each media source that has an img dir."""

    by_media_source: tuple[tuple[MediaSource, JpegCheck], ...]

    @property
    def success(self) -> bool:
        """Return whether every media source's JPEG check passed."""
        return all(check.success for _, check in self.by_media_source)


def _expected_jpeg_name(heic_filename: str) -> str | None:
    """Return the JPEG name a main-img file converts to, or None if it does not."""
    ext = file_ext(heic_filename)
    match True:
        case _ if ext in CONVERT_TO_JPEG_EXTENSIONS:
            return Path(heic_filename).with_suffix(".jpg").name
        case _ if ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
            return heic_filename
        case _:
            return None


def check_jpeg_dir(
    main_img_dir: Path,
    main_jpg_dir: Path,
    *,
    on_file_checked: FileEnd | None = None,
) -> JpegCheck:
    """
    Check that *main_jpg_dir* holds one JPEG per image of *main_img_dir*.

    Convertible images expect a ``.jpg`` of the same stem, and JPEG and
    PNG images expect a copy of the same name; other files expect nothing.
    *on_file_checked* is called with each present (``True``), missing or
    extra (``False``) JPEG name.
    """
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

    if on_file_checked:
        for name in present:
            on_file_checked(name, success=True)
        for name in missing:
            on_file_checked(name, success=False)
        for name in extra:
            on_file_checked(name, success=False)

    return JpegCheck(
        present=tuple(present),
        missing=tuple(missing),
        extra=tuple(extra),
    )


def check_album_jpeg_integrity(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> AlbumJpegIntegrityResult:
    """Only checks media sources that have a ``{name}-img/`` directory."""
    return AlbumJpegIntegrityResult(
        by_media_source=tuple(
            (
                ms,
                check_jpeg_dir(album_dir / ms.img_dir, album_dir / ms.jpg_dir),
            )
            for ms in media_sources
            if (album_dir / ms.img_dir).is_dir()
        ),
    )
