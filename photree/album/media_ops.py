"""Move and remove media files across album contributor directories.

Given relative file paths (as reported by ``album check``), resolves all
associated variants by image number (iOS) or filename stem (plain) and
moves or deletes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..fsprotocol import (
    VID_EXTENSIONS,
    Contributor,
    delete_files,
    discover_contributors,
    file_ext,
    find_files_by_number,
    find_files_by_stem,
    img_number,
    move_files,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MediaOpResult:
    """Result of a move or remove operation."""

    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        return sum(len(files) for _, files in self.files_by_dir)


# ---------------------------------------------------------------------------
# Directory-to-contributor mapping
# ---------------------------------------------------------------------------


def _build_dir_to_contributor(
    contributors: list[Contributor],
) -> dict[str, Contributor]:
    """Map every contributor subdirectory name to its contributor."""
    mapping: dict[str, Contributor] = {}
    for c in contributors:
        for d in c.all_subdirs:
            mapping[d] = c
    return mapping


# ---------------------------------------------------------------------------
# Variant resolution
# ---------------------------------------------------------------------------


def _dirs_for_images(contrib: Contributor) -> tuple[str, ...]:
    if contrib.is_ios:
        return (
            contrib.orig_img_dir,
            contrib.edit_img_dir,
            contrib.img_dir,
            contrib.jpg_dir,
        )
    return (contrib.img_dir, contrib.jpg_dir)


def _dirs_for_videos(contrib: Contributor) -> tuple[str, ...]:
    if contrib.is_ios:
        return (contrib.orig_vid_dir, contrib.edit_vid_dir, contrib.vid_dir)
    return (contrib.vid_dir,)


def _is_video(filename: str) -> bool:
    return file_ext(filename) in VID_EXTENSIONS


def _find_matching_files(
    album_dir: Path,
    subdir: str,
    keys: set[str],
    *,
    use_stem: bool,
) -> list[str]:
    """Find files in *album_dir/subdir* matching *keys*.

    When *use_stem* is True, matches by filename stem (plain contributors).
    Otherwise matches by image number (iOS contributors).
    """
    directory = album_dir / subdir
    if not directory.is_dir():
        return []
    if use_stem:
        return find_files_by_stem(keys, directory)
    return find_files_by_number(keys, directory)


def resolve_variants(
    album_dir: Path,
    relative_paths: list[str],
) -> list[tuple[str, list[str]]]:
    """Resolve all file variants for the given relative paths.

    Returns ``[(subdir, [filename, ...])]`` with all variant files found
    across the contributor directory structure.
    """
    contributors = discover_contributors(album_dir)
    if not contributors:
        raise ValueError(f"No contributors found in {album_dir}")

    dir_to_contrib = _build_dir_to_contributor(contributors)

    # Group input paths by (contributor, is_video) → set of match keys
    groups: dict[tuple[str, bool], set[str]] = {}
    contrib_by_name: dict[str, Contributor] = {}

    for rel_path in relative_paths:
        parts = Path(rel_path).parts
        if len(parts) < 2:
            raise ValueError(
                f'"{rel_path}" must be a relative path with a directory'
                " (e.g. main-jpg/IMG_E3219.jpg)"
            )
        # Handle both flat (main-jpg/file) and nested (ios-main/orig-img/file) dirs
        subdir = str(Path(*parts[:-1]))
        filename = parts[-1]

        contrib = dir_to_contrib.get(subdir)
        if contrib is None:
            raise ValueError(
                f'directory "{subdir}" does not match any contributor in {album_dir}'
            )

        video = _is_video(filename)
        use_stem = not contrib.is_ios
        key = Path(filename).stem if use_stem else img_number(filename)

        group_key = (contrib.name, video)
        groups.setdefault(group_key, set()).add(key)
        contrib_by_name[contrib.name] = contrib

    # Resolve variants across all directories
    result: list[tuple[str, list[str]]] = []
    for (contrib_name, video), keys in groups.items():
        contrib = contrib_by_name[contrib_name]
        dirs = _dirs_for_videos(contrib) if video else _dirs_for_images(contrib)
        use_stem = not contrib.is_ios

        for subdir in dirs:
            files = _find_matching_files(album_dir, subdir, keys, use_stem=use_stem)
            if files:
                result.append((subdir, files))

    return result


# ---------------------------------------------------------------------------
# Move / Remove
# ---------------------------------------------------------------------------


def _remove_empty_dirs(
    album_dir: Path,
    subdirs: list[str],
    *,
    dry_run: bool,
) -> None:
    """Remove subdirectories that are now empty after a move/rm operation."""
    for subdir in subdirs:
        directory = album_dir / subdir
        if directory.is_dir() and not any(directory.iterdir()):
            if not dry_run:
                directory.rmdir()
                # Also remove parent if it's an iOS nested dir (e.g. ios-main/orig-img)
                parent = directory.parent
                if (
                    parent != album_dir
                    and parent.is_dir()
                    and not any(parent.iterdir())
                ):
                    parent.rmdir()


def move_media(
    source_album: Path,
    dest_album: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> MediaOpResult:
    """Move media files and all their variants from *source_album* to *dest_album*."""
    variants = resolve_variants(source_album, relative_paths)

    moved: list[tuple[str, tuple[str, ...]]] = []
    for subdir, files in variants:
        move_files(
            source_album / subdir,
            dest_album / subdir,
            files,
            dry_run=dry_run,
            log_cwd=log_cwd,
        )
        moved.append((subdir, tuple(files)))

    _remove_empty_dirs(source_album, [subdir for subdir, _ in moved], dry_run=dry_run)
    return MediaOpResult(files_by_dir=tuple(moved))


def rm_media(
    album_dir: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> MediaOpResult:
    """Remove media files and all their variants from *album_dir*."""
    variants = resolve_variants(album_dir, relative_paths)

    removed: list[tuple[str, tuple[str, ...]]] = []
    for subdir, files in variants:
        delete_files(
            album_dir / subdir,
            files,
            dry_run=dry_run,
            log_cwd=log_cwd,
        )
        removed.append((subdir, tuple(files)))

    _remove_empty_dirs(album_dir, [subdir for subdir, _ in removed], dry_run=dry_run)
    return MediaOpResult(files_by_dir=tuple(removed))
