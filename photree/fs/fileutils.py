"""Generic file utilities (not photree-specific)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path


def display_path(path: Path, cwd: Path) -> Path:
    """Return *path* relative to *cwd* when possible, otherwise unchanged."""
    return path.relative_to(cwd) if path.is_relative_to(cwd) else path


def list_files(directory: Path) -> list[str]:
    """Return regular filenames in *directory*, excluding dotfiles (e.g. .DS_Store).

    Returns an empty list when *directory* does not exist.
    """
    if not directory.is_dir():
        return []
    return sorted(
        f
        for f in os.listdir(directory)
        if not f.startswith(".") and (directory / f).is_file()
    )


def file_ext(filename: str) -> str:
    """Return the lowercased file extension (e.g. ``".heic"``)."""
    return Path(filename).suffix.lower()


def count_unique_media_numbers(directory: Path, extensions: frozenset[str]) -> int:
    """Count unique image numbers among media files in *directory*."""
    return len(
        {
            "".join(c for c in f if c.isdigit())
            for f in list_files(directory)
            if Path(f).suffix.lower() in extensions
        }
    )


def _visible_subdirs(directory: Path) -> Iterator[Path]:
    """Yield visible (non-dot) subdirectories of *directory*, sorted by name."""
    return (
        child
        for child in sorted(directory.iterdir())
        if child.is_dir() and not child.name.startswith(".")
    )


def matching_subdirectories(
    base_dir: Path, predicate: Callable[[Path], bool]
) -> list[Path]:
    """Recursively collect subdirectories of *base_dir* that satisfy *predicate*.

    When a directory matches, it is collected and its subtree is not descended
    into. *base_dir* itself is never returned.
    """

    def walk(directory: Path) -> Iterator[Path]:
        if predicate(directory):
            yield directory
        else:
            for child in _visible_subdirs(directory):
                yield from walk(child)

    return list(walk(base_dir))
