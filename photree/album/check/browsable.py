"""Browsable directory consistency checks.

Verifies that ``{name}-img/`` and ``{name}-vid/`` contain the correct files
derived from the archive's orig and edited sources.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_files
from ...fsprotocol import LinkMode
from ..store.media_sources import dedup_media_dict
from ..store.protocol import _KeyFn


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
class WrongLinkMode:
    """A file with correct content but wrong link type."""

    filename: str
    expected: str  # "hardlink", "symlink", or "copy"
    actual: str  # "hardlink", "symlink", or "copy"


@dataclass(frozen=True)
class BrowsableDirCheck:
    """Result of checking a browsable directory against archive orig/edited."""

    correct: tuple[FileComparison, ...]
    missing: tuple[MissingFile, ...]
    extra: tuple[str, ...]
    wrong_source: tuple[str, ...]
    wrong_link_mode: tuple[WrongLinkMode, ...]
    size_mismatches: tuple[FileComparison, ...]
    checksum_mismatches: tuple[FileComparison, ...]

    @property
    def success(self) -> bool:
        return (
            not self.missing
            and not self.extra
            and not self.wrong_source
            and not self.wrong_link_mode
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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


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


_LINK_MODE_NAMES: dict[LinkMode, str] = {
    LinkMode.HARDLINK: "hardlink",
    LinkMode.SYMLINK: "symlink",
    LinkMode.COPY: "copy",
}


def _detect_actual_link_mode(main_path: Path, source_path: Path) -> str:
    """Return the actual link mode of *main_path* relative to *source_path*."""
    if _is_symlink_to(main_path, source_path):
        return "symlink"
    if _is_hardlink_to(main_path, source_path):
        return "hardlink"
    return "copy"


def _compare_file(
    main_path: Path,
    source_path: Path,
    *,
    link_mode: LinkMode,
    checksum: bool,
) -> tuple[FileComparison, WrongLinkMode | None]:
    """Compare a main file against its expected source.

    Returns a ``(comparison, wrong_link_mode)`` tuple. If the file uses
    the wrong link type, *wrong_link_mode* is set but the comparison may
    still succeed (content is correct, just the link type is wrong).

    If the main file is a hardlink or symlink to the source, content
    verification is skipped (the link guarantees correctness).
    """
    actual = _detect_actual_link_mode(main_path, source_path)
    expected = _LINK_MODE_NAMES[link_mode]
    wrong_lm = (
        WrongLinkMode(filename=main_path.name, expected=expected, actual=actual)
        if actual != expected
        else None
    )

    is_link = actual in ("hardlink", "symlink")
    if is_link:
        return (
            FileComparison(
                filename=main_path.name,
                expected_source=source_path.name,
                size_match=True,
                checksum_match=True if checksum else None,
                link_verified=True,
            ),
            wrong_lm,
        )

    size_match = _file_size(main_path) == _file_size(source_path)
    match (checksum, size_match):
        case (False, _):
            checksum_match = None
        case (True, False):
            checksum_match = False
        case (True, True):
            checksum_match = _file_sha256(main_path) == _file_sha256(source_path)

    return (
        FileComparison(
            filename=main_path.name,
            expected_source=source_path.name,
            size_match=size_match,
            checksum_match=checksum_match,
        ),
        wrong_lm,
    )


def _classify_expected_file(
    expected_name: str,
    source_name: str,
    source_dir: Path,
    browsable_dir: Path,
    browsable_files: set[str],
    *,
    link_mode: LinkMode,
    checksum: bool,
    on_file_checked: Callable[[str, bool], None] | None,
) -> tuple[
    list[FileComparison],  # correct
    list[MissingFile],  # missing
    list[WrongLinkMode],  # wrong_link_mode
    list[FileComparison],  # size_mismatches
    list[FileComparison],  # checksum_mismatches
]:
    """Classify a single expected file against the main directory."""
    if expected_name not in browsable_files:
        if on_file_checked:
            on_file_checked(expected_name, False)
        return [], [MissingFile(expected_name, source_dir.name)], [], [], []

    comparison, wrong_lm = _compare_file(
        browsable_dir / expected_name,
        source_dir / source_name,
        link_mode=link_mode,
        checksum=checksum,
    )

    if not comparison.size_match:
        if on_file_checked:
            on_file_checked(expected_name, False)
        return [], [], [wrong_lm] if wrong_lm else [], [comparison], []
    elif comparison.checksum_match is False:
        if on_file_checked:
            on_file_checked(expected_name, False)
        return [], [], [wrong_lm] if wrong_lm else [], [], [comparison]
    else:
        if on_file_checked:
            on_file_checked(expected_name, True)
        return [comparison], [], [wrong_lm] if wrong_lm else [], [], []


# ---------------------------------------------------------------------------
# Check function
# ---------------------------------------------------------------------------


def check_browsable_dir(
    orig_dir: Path,
    edit_dir: Path,
    browsable_dir: Path,
    *,
    media_extensions: frozenset[str],
    key_fn: _KeyFn,
    link_mode: LinkMode,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> BrowsableDirCheck:
    """Check that a browsable directory is consistent with orig/edited.

    For each media key in orig_dir, the browsable_dir should contain
    either the edited variant (if one exists in edit_dir) or the original.
    Files are matched using *key_fn* (image number for iOS, stem for std).

    When *link_mode* is ``HARDLINK`` or ``SYMLINK``, also verifies that
    each file uses the expected link type. Files with correct content but
    wrong link type are reported as ``wrong_link_mode``.
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)
    browsable_files = set(list_files(browsable_dir))

    # Use priority dedup to handle duplicate keys (e.g. IMG_E7658.JPG + IMG_E7658.HEIC)
    orig_media_by_number = dedup_media_dict(orig_files, media_extensions, key_fn)
    edit_media_by_number = dedup_media_dict(edit_files, media_extensions, key_fn)

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
            link_mode=link_mode,
            checksum=checksum,
            on_file_checked=on_file_checked,
        )
        for expected_name, (source_name, source_dir) in sorted(expected.items())
    ]

    correct = [c for cls in classifications for c in cls[0]]
    missing = [m for cls in classifications for m in cls[1]]
    wrong_link_mode = [w for cls in classifications for w in cls[2]]
    size_mismatches = [s for cls in classifications for s in cls[3]]
    checksum_mismatches = [c for cls in classifications for c in cls[4]]

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
        wrong_link_mode=tuple(wrong_link_mode),
        size_mismatches=tuple(size_mismatches),
        checksum_mismatches=tuple(checksum_mismatches),
    )
