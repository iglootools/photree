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
from ..store.media_sources import ios_dedup_media_dict as dedup_media_dict


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


# ---------------------------------------------------------------------------
# Check function
# ---------------------------------------------------------------------------


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
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)
    browsable_files = set(list_files(browsable_dir))

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
