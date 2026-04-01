"""Move and remove media files across album media source directories.

Given relative file paths (as reported by ``album check``), resolves all
associated variants by image number (iOS) or filename stem (std) and
moves or deletes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..fs import (
    VID_EXTENSIONS,
    MediaSource,
    delete_files,
    discover_media_sources,
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
# Directory-to-media-source mapping
# ---------------------------------------------------------------------------


def _build_dir_to_media_source(
    media_sources: list[MediaSource],
) -> dict[str, MediaSource]:
    """Map every media source subdirectory name to its media source."""
    mapping: dict[str, MediaSource] = {}
    for ms in media_sources:
        for d in ms.all_subdirs:
            mapping[d] = ms
    return mapping


# ---------------------------------------------------------------------------
# Variant resolution
# ---------------------------------------------------------------------------


def _dirs_for_images(ms: MediaSource) -> tuple[str, ...]:
    return (
        ms.orig_img_dir,
        ms.edit_img_dir,
        ms.img_dir,
        ms.jpg_dir,
    )


def _dirs_for_videos(ms: MediaSource) -> tuple[str, ...]:
    return (ms.orig_vid_dir, ms.edit_vid_dir, ms.vid_dir)


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

    When *use_stem* is True, matches by filename stem (std media sources).
    Otherwise matches by image number (iOS media sources).
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
    across the media source directory structure.
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        raise ValueError(f"No media sources found in {album_dir}")

    dir_to_ms = _build_dir_to_media_source(media_sources)

    # Group input paths by (media_source, is_video) → set of match keys
    groups: dict[tuple[str, bool], set[str]] = {}
    ms_by_name: dict[str, MediaSource] = {}

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

        ms = dir_to_ms.get(subdir)
        if ms is None:
            raise ValueError(
                f'directory "{subdir}" does not match any media source in {album_dir}'
            )

        video = _is_video(filename)
        use_stem = not ms.is_ios
        key = Path(filename).stem if use_stem else img_number(filename)

        group_key = (ms.name, video)
        groups.setdefault(group_key, set()).add(key)
        ms_by_name[ms.name] = ms

    # Resolve variants across all directories
    result: list[tuple[str, list[str]]] = []
    for (ms_name, video), keys in groups.items():
        ms = ms_by_name[ms_name]
        dirs = _dirs_for_videos(ms) if video else _dirs_for_images(ms)
        use_stem = not ms.is_ios

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

    # Fail fast before moving anything if the destination already contains
    # files with the same image number (iOS) or stem (std).
    dest_media_sources = discover_media_sources(dest_album)
    dest_dir_to_ms = _build_dir_to_media_source(dest_media_sources)

    incoming_keys_by_subdir: dict[str, set[str]] = {}
    for subdir, files in variants:
        ms = dest_dir_to_ms.get(subdir)
        use_stem = ms is not None and not ms.is_ios
        keys = (
            {Path(f).stem for f in files}
            if use_stem
            else {img_number(f) for f in files}
        )
        incoming_keys_by_subdir[subdir] = keys

    conflicts = sorted(
        {
            f"{subdir}/{existing}"
            for subdir, keys in incoming_keys_by_subdir.items()
            for existing in _find_matching_files(
                dest_album,
                subdir,
                keys,
                use_stem=subdir in dest_dir_to_ms and not dest_dir_to_ms[subdir].is_ios,
            )
        }
    )
    if conflicts:
        raise ValueError(
            f"Move would conflict with {len(conflicts)} existing file(s) "
            f"in {dest_album.name}:\n"
            + "".join(f"  {c}\n" for c in conflicts[:10])
            + (f"  ... and {len(conflicts) - 10} more\n" if len(conflicts) > 10 else "")
            + "Use a different media source to avoid conflicts."
        )

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
