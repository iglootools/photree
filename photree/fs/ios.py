"""iOS Image Capture naming conventions and media file helpers."""

from __future__ import annotations

from pathlib import Path

from .fileutils import file_ext, list_files

# Preferred formats when multiple variants exist for the same image number.
# DNG (ProRAW) is the highest-quality format, followed by HEIC (native iPhone).
# Handles the iOS edge case where both JPG and HEIC/DNG variants exist
# for the same edited photo (e.g. IMG_E7658.JPG + IMG_E7658.HEIC).
# Tuple (not set) to express priority order: first match wins.
PICTURE_PRIORITY_EXTENSIONS = (".dng", ".heic")


def img_number(filename: str) -> str:
    """Extract the numeric portion of a filename (e.g. ``"0410"`` from ``"IMG_0410.HEIC"``)."""
    return "".join(c for c in filename if c.isdigit())


def pick_media_priority(candidates: list[str]) -> str:
    """Pick the highest-priority file from candidates (DNG > HEIC > others)."""
    return next(
        (
            f
            for ext in PICTURE_PRIORITY_EXTENSIONS
            for f in candidates
            if file_ext(f) == ext
        ),
        candidates[0],
    )


def _group_by_number(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, list[str]]:
    """Group media files by their numeric ID."""
    groups: dict[str, list[str]] = {}
    for f in files:
        if file_ext(f) in media_extensions:
            groups.setdefault(img_number(f), []).append(f)
    return groups


def dedup_media_dict(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, str]:
    """Build a number→filename dict, preferring DNG > HEIC when duplicates exist.

    Handles an undocumented iOS edge case where Image Capture exports multiple
    format variants for the same numeric ID (e.g. IMG_E7658.JPG + IMG_E7658.HEIC).
    This can happen with airdrops, photo downloads, screenshots, or similar use
    cases that share a numeric ID with a camera-taken photo. The priority order
    (DNG > HEIC > others) picks the highest-quality format.
    """
    return {
        num: (pick_media_priority(candidates) if len(candidates) > 1 else candidates[0])
        for num, candidates in _group_by_number(files, media_extensions).items()
    }


def find_files_by_number(
    numbers: set[str],
    directory: Path,
) -> list[str]:
    """Find all files in *directory* whose image number is in *numbers*."""
    return sorted(f for f in list_files(directory) if img_number(f) in numbers)


def find_files_by_stem(
    stems: set[str],
    directory: Path,
) -> list[str]:
    """Find all files in *directory* whose stem (name without extension) is in *stems*."""
    return sorted(f for f in list_files(directory) if Path(f).stem in stems)
