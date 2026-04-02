"""Album integrity checks.

Generic checks (all media source types):
- Browsable dir consistency: {name}-img/{name}-vid contain the right
  files derived from orig/edited sources
- JPEG completeness: {name}-jpg mirrors {name}-img with a JPEG
  counterpart for every file

iOS-specific checks:
- AAE sidecar validation (missing/orphan sidecars)
- Duplicate image numbers within the same prefix category
- Miscategorized files (edited in orig dirs or vice versa)
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_files
from ..store.media_sources_discovery import discover_media_sources
from ..store.media_sources import ios_dedup_media_dict as dedup_media_dict
from ..store.protocol import (
    CONVERT_TO_JPEG_EXTENSIONS,
    COPY_AS_IS_TO_JPEG_EXTENSIONS,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    MediaSource,
)


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _is_media(filename: str) -> bool:
    ext = _ext(filename)
    return ext in IOS_IMG_EXTENSIONS or ext in IOS_VID_EXTENSIONS


def _img_number(filename: str) -> str:
    return "".join(c for c in filename if c.isdigit())


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _list_files(directory: Path) -> list[str]:
    return list_files(directory)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileComparison:
    """Result of comparing a main file against its expected source."""

    filename: str
    expected_source: str
    size_match: bool
    checksum_match: bool | None  # None if checksum not requested
    link_verified: bool = False  # True if verified via hardlink inode or symlink target


@dataclass(frozen=True)
class MissingFile:
    """A file expected in main but not found."""

    filename: str
    source_dir: str  # e.g. "edit-img" or "orig-img"


@dataclass(frozen=True)
class BrowsableDirCheck:
    """Result of checking a browsable directory against archive orig/edited."""

    correct: tuple[FileComparison, ...]
    missing: tuple[MissingFile, ...]
    extra: tuple[str, ...]
    wrong_source: tuple[str, ...]
    size_mismatches: tuple[FileComparison, ...]
    checksum_mismatches: tuple[FileComparison, ...]

    @property
    def success(self) -> bool:
        return (
            not self.missing
            and not self.extra
            and not self.wrong_source
            and not self.size_mismatches
            and not self.checksum_mismatches
        )

    @property
    def files_match_sources(self) -> bool:
        """True when every present file matches its archival source.

        Unlike :attr:`success`, missing and extra files are tolerated —
        only content mismatches (size or checksum) are considered a
        failure. This catches the case where a browsable file has been
        corrupted or replaced with different content.
        """
        return not self.size_mismatches and not self.checksum_mismatches


@dataclass(frozen=True)
class JpegCheck:
    """Result of checking main-jpg against main-img."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def success(self) -> bool:
        return not self.missing and not self.extra


def check_miscategorized_files(
    orig_dir: Path,
    edit_dir: Path,
) -> tuple[str, ...]:
    """Check for edited files in orig dirs and original files in edit dirs.

    Orig dirs should contain only original files (IMG_XXXX prefix).
    Edit dirs should contain only edited files (IMG_E/IMG_O prefix).
    """
    orig_files = _list_files(orig_dir)
    edit_files = _list_files(edit_dir)

    return tuple(
        [
            *[
                f"{f} in {orig_dir.name}/ looks like an edited file (IMG_E prefix)"
                for f in sorted(orig_files)
                if _is_media(f) and _file_prefix(f) == "E"
            ],
            *[
                f"{f} in {orig_dir.name}/ looks like an edited sidecar (IMG_O prefix)"
                for f in sorted(orig_files)
                if _file_prefix(f) == "O"
            ],
            *[
                f"{f} in {edit_dir.name}/ looks like an original file (no E/O prefix)"
                for f in sorted(edit_files)
                if _is_media(f) and _file_prefix(f) == ""
            ],
            *[
                f"{f} in {edit_dir.name}/ looks like an original sidecar (no E/O prefix)"
                for f in sorted(edit_files)
                if not _is_media(f) and _file_prefix(f) == ""
            ],
        ]
    )


@dataclass(frozen=True)
class IosAlbumIntegrityResult:
    """Full integrity check result for an iOS album."""

    browsable_heic: BrowsableDirCheck
    browsable_mov: BrowsableDirCheck
    jpeg: JpegCheck
    sidecars: SidecarCheck
    duplicate_numbers: tuple[str, ...] = ()
    miscategorized: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        # missing_sidecars are not checked here: iOS does not always produce
        # AAE sidecars (e.g. no edits applied, older iOS versions), so their
        # absence is informational, not an error.
        # Use has_warnings to detect these; --fatal-warnings promotes them.
        return (
            self.browsable_heic.success
            and self.browsable_mov.success
            and self.jpeg.success
            and not self.sidecars.orphan_sidecars
            and not self.duplicate_numbers
            and not self.miscategorized
        )

    @property
    def has_warnings(self) -> bool:
        """True if there are informational warnings (e.g. missing sidecars)."""
        return bool(self.sidecars.missing_sidecars)


@dataclass(frozen=True)
class IosAlbumFullIntegrityResult:
    """Full integrity check result across all contributors."""

    by_media_source: tuple[tuple[MediaSource, IosAlbumIntegrityResult], ...]

    @property
    def success(self) -> bool:
        return all(result.success for _, result in self.by_media_source)

    @property
    def has_warnings(self) -> bool:
        return any(result.has_warnings for _, result in self.by_media_source)


@dataclass(frozen=True)
class AlbumJpegIntegrityResult:
    """JPEG integrity check result across all contributors (iOS + std)."""

    by_media_source: tuple[tuple[MediaSource, JpegCheck], ...]

    @property
    def success(self) -> bool:
        return all(check.success for _, check in self.by_media_source)


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _file_prefix(filename: str) -> str:
    """Extract the prefix category of an iOS filename.

    IMG_E → 'E' (edited), IMG_O → 'O' (edited metadata), IMG_ → '' (original).
    """
    lower = filename.lower()
    if lower.startswith("img_e"):
        return "E"
    elif lower.startswith("img_o"):
        return "O"
    else:
        return ""


def check_duplicate_numbers(
    directory: Path, media_extensions: frozenset[str]
) -> tuple[str, ...]:
    """Check for duplicate media file numbers within the same prefix category.

    IMG_7552.HEIC + IMG_E7552.HEIC sharing number 7552 is normal (original + edited).
    IMG_E7658.HEIC + IMG_E7658.JPG sharing number 7658 within the same 'E' prefix is a duplicate.
    """
    files = _list_files(directory)
    # Group by (prefix, number) — only flag duplicates within the same prefix
    by_prefix_number: dict[tuple[str, str], list[str]] = {}
    for f in files:
        if _ext(f) in media_extensions:
            key = (_file_prefix(f), _img_number(f))
            by_prefix_number.setdefault(key, []).append(f)

    return tuple(
        f"{directory.name}/: number {num} has multiple media files "
        f"with same prefix: {', '.join(candidates)}"
        for (prefix, num), candidates in sorted(by_prefix_number.items())
        if len(candidates) > 1
    )


def _is_hardlink_to(main_path: Path, source_path: Path) -> bool:
    """Check whether *main_path* is a hardlink to *source_path* (same inode)."""
    return os.stat(main_path).st_ino == os.stat(source_path).st_ino


def _is_symlink_to(main_path: Path, source_path: Path) -> bool:
    """Check whether *main_path* is a symlink that resolves to *source_path*."""
    return main_path.is_symlink() and main_path.resolve() == source_path.resolve()


def _is_link_to(main_path: Path, source_path: Path) -> bool:
    """Check whether *main_path* is a hardlink or symlink to *source_path*."""
    return _is_symlink_to(main_path, source_path) or _is_hardlink_to(
        main_path, source_path
    )


def _compare_file(
    main_path: Path,
    source_path: Path,
    *,
    checksum: bool,
) -> FileComparison:
    """Compare a main file against its expected source.

    If the main file is a hardlink or symlink to the source, the comparison
    succeeds immediately without checking size or checksum.
    """
    if _is_link_to(main_path, source_path):
        return FileComparison(
            filename=main_path.name,
            expected_source=source_path.name,
            size_match=True,
            checksum_match=True if checksum else None,
            link_verified=True,
        )
    else:
        size_match = _file_size(main_path) == _file_size(source_path)
        match (checksum, size_match):
            case (False, _):
                checksum_match = None
            case (True, False):
                checksum_match = False
            case (True, True):
                checksum_match = _file_sha256(main_path) == _file_sha256(source_path)

        return FileComparison(
            filename=main_path.name,
            expected_source=source_path.name,
            size_match=size_match,
            checksum_match=checksum_match,
        )


def _expected_jpeg_name(heic_filename: str) -> str | None:
    """Return the expected JPEG filename for a main-img file, or None if not convertible."""
    ext = _ext(heic_filename)
    match True:
        case _ if ext in CONVERT_TO_JPEG_EXTENSIONS:
            return Path(heic_filename).with_suffix(".jpg").name
        case _ if ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
            return heic_filename
        case _:
            return None


def _classify_expected_file(
    expected_name: str,
    source_name: str,
    source_dir: Path,
    browsable_dir: Path,
    browsable_files: set[str],
    *,
    checksum: bool,
    on_file_checked: Callable[[str, bool], None] | None,
) -> tuple[
    list[FileComparison],  # correct
    list[MissingFile],  # missing
    list[FileComparison],  # size_mismatches
    list[FileComparison],  # checksum_mismatches
]:
    """Classify a single expected file against the main directory."""
    if expected_name not in browsable_files:
        if on_file_checked:
            on_file_checked(expected_name, False)
        return [], [MissingFile(expected_name, source_dir.name)], [], []

    comparison = _compare_file(
        browsable_dir / expected_name,
        source_dir / source_name,
        checksum=checksum,
    )

    if not comparison.size_match:
        if on_file_checked:
            on_file_checked(expected_name, False)
        return [], [], [comparison], []
    elif comparison.checksum_match is False:
        if on_file_checked:
            on_file_checked(expected_name, False)
        return [], [], [], [comparison]
    else:
        if on_file_checked:
            on_file_checked(expected_name, True)
        return [comparison], [], [], []


def check_browsable_dir(
    orig_dir: Path,
    edit_dir: Path,
    browsable_dir: Path,
    *,
    media_extensions: frozenset[str],
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> BrowsableDirCheck:
    """Check that a browsable directory is consistent with orig/edited.

    For each media key in orig_dir, the browsable_dir should contain
    either the edited variant (if one exists in edit_dir) or the original.
    """
    orig_files = _list_files(orig_dir)
    edit_files = _list_files(edit_dir)
    browsable_files = set(_list_files(browsable_dir))

    # Use priority dedup to handle duplicate keys (e.g. IMG_E7658.JPG + IMG_E7658.HEIC)
    orig_media_by_number = dedup_media_dict(orig_files, media_extensions)
    edit_media_by_number = dedup_media_dict(edit_files, media_extensions)

    # Determine what should be in main: edited if available, else original
    expected: dict[str, tuple[str, Path]] = {
        **(
            {
                edit_media_by_number[num]: (
                    edit_media_by_number[num],
                    edit_dir,
                )
                for num in orig_media_by_number
                if num in edit_media_by_number
            }
        ),
        **(
            {
                orig_name: (orig_name, orig_dir)
                for num, orig_name in orig_media_by_number.items()
                if num not in edit_media_by_number
            }
        ),
    }

    # Classify each expected file
    classifications = [
        _classify_expected_file(
            expected_name,
            source_name,
            source_dir,
            browsable_dir,
            browsable_files,
            checksum=checksum,
            on_file_checked=on_file_checked,
        )
        for expected_name, (source_name, source_dir) in sorted(expected.items())
    ]

    correct = [c for cls in classifications for c in cls[0]]
    missing = [m for cls in classifications for m in cls[1]]
    size_mismatches = [s for cls in classifications for s in cls[2]]
    checksum_mismatches = [c for cls in classifications for c in cls[3]]

    # Wrong source: orig in main when edited version exists
    wrong_source = [
        f"{orig_media_by_number[num]} (should be {edit_name}, edited version exists)"
        for num, edit_name in edit_media_by_number.items()
        if (orig_name := orig_media_by_number.get(num))
        and orig_name in browsable_files
        and orig_name != edit_name
    ]

    # Extra files in main that shouldn't be there
    extra = sorted(browsable_files - set(expected.keys()))

    return BrowsableDirCheck(
        correct=tuple(correct),
        missing=tuple(missing),
        extra=tuple(extra),
        wrong_source=tuple(wrong_source),
        size_mismatches=tuple(size_mismatches),
        checksum_mismatches=tuple(checksum_mismatches),
    )


def check_jpeg_dir(
    main_img_dir: Path,
    main_jpg_dir: Path,
    *,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> JpegCheck:
    """Check that main-jpg has a counterpart for every file in main-img."""
    heic_files = _list_files(main_img_dir)
    jpeg_files = set(_list_files(main_jpg_dir))

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


@dataclass(frozen=True)
class SidecarCheck:
    """Result of checking AAE sidecars in orig and edit directories."""

    missing_sidecars: tuple[str, ...]
    orphan_sidecars: tuple[str, ...]


def check_sidecars(
    orig_dir: Path,
    edit_dir: Path,
) -> SidecarCheck:
    """Check for missing and orphan AAE sidecars in orig and edit directories."""
    orig_files = set(_list_files(orig_dir))
    edit_files = set(_list_files(edit_dir))

    orig_media_numbers = {_img_number(f) for f in orig_files if _is_media(f)}
    edit_media_numbers = {
        _img_number(f)
        for f in edit_files
        if _is_media(f) and f.upper().startswith("IMG_E")
    }

    missing_sidecars = tuple(
        [
            # Each HEIC in orig should have an AAE sidecar
            *[
                f"{f} has no AAE sidecar in {orig_dir.name}/"
                for f in sorted(orig_files)
                if _ext(f) == ".heic" and f"IMG_{_img_number(f)}.AAE" not in orig_files
            ],
            # Each edited media file should have an O-prefixed AAE sidecar
            *[
                f"{f} has no O-prefixed AAE sidecar in {edit_dir.name}/"
                for f in sorted(edit_files)
                if _is_media(f)
                and f.upper().startswith("IMG_E")
                and f"IMG_O{_img_number(f)}.AAE" not in edit_files
            ],
        ]
    )

    orphan_sidecars = tuple(
        [
            # Orphan AAE sidecars in orig (no matching media file)
            *[
                f"{f} has no matching media file in {orig_dir.name}/"
                for f in sorted(orig_files)
                if _ext(f) in SIDECAR_EXTENSIONS
                and _img_number(f) not in orig_media_numbers
            ],
            # Orphan O-prefixed AAE sidecars in edit (no matching edited media)
            *[
                f"{f} has no matching edited media file in {edit_dir.name}/"
                for f in sorted(edit_files)
                if _ext(f) in SIDECAR_EXTENSIONS
                and f.upper().startswith("IMG_O")
                and _img_number(f) not in edit_media_numbers
            ],
        ]
    )

    return SidecarCheck(
        missing_sidecars=missing_sidecars,
        orphan_sidecars=orphan_sidecars,
    )


def check_ios_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> IosAlbumIntegrityResult:
    """Run all integrity checks for a single media source within an iOS album."""
    assert ms.is_ios, "integrity checks require an iOS media source"
    browsable_heic = check_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=IOS_IMG_EXTENSIONS,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    browsable_mov = check_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        album_dir / ms.vid_dir,
        media_extensions=IOS_VID_EXTENSIONS,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    jpeg = check_jpeg_dir(
        album_dir / ms.img_dir,
        album_dir / ms.jpg_dir,
    )

    heic_sidecars = check_sidecars(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
    )
    mov_sidecars = check_sidecars(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
    )
    sidecars = SidecarCheck(
        missing_sidecars=(
            *heic_sidecars.missing_sidecars,
            *mov_sidecars.missing_sidecars,
        ),
        orphan_sidecars=(
            *heic_sidecars.orphan_sidecars,
            *mov_sidecars.orphan_sidecars,
        ),
    )

    all_media = IOS_IMG_EXTENSIONS | IOS_VID_EXTENSIONS
    duplicate_numbers = tuple(
        w
        for subdir_name in ms.all_subdirs
        if (album_dir / subdir_name).is_dir()
        for w in check_duplicate_numbers(album_dir / subdir_name, all_media)
    )

    miscategorized = (
        *check_miscategorized_files(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
        ),
        *check_miscategorized_files(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
        ),
    )

    return IosAlbumIntegrityResult(
        browsable_heic=browsable_heic,
        browsable_mov=browsable_mov,
        jpeg=jpeg,
        sidecars=sidecars,
        duplicate_numbers=duplicate_numbers,
        miscategorized=miscategorized,
    )


def check_ios_album_integrity(
    album_dir: Path,
    *,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> IosAlbumFullIntegrityResult:
    """Run integrity checks for all iOS media sources in an album."""
    ios_sources = [ms for ms in discover_media_sources(album_dir) if ms.is_ios]
    return IosAlbumFullIntegrityResult(
        by_media_source=tuple(
            (
                ms,
                check_ios_media_source_integrity(
                    album_dir,
                    ms,
                    checksum=checksum,
                    on_file_checked=on_file_checked,
                ),
            )
            for ms in ios_sources
        )
    )


def check_album_jpeg_integrity(
    album_dir: Path,
) -> AlbumJpegIntegrityResult:
    """Check ``{name}-jpg/`` for every media source (iOS + std).

    Only checks media sources that have a ``{name}-img/`` directory.
    """
    media_sources = discover_media_sources(album_dir)
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
