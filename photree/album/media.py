"""Move and remove media files across album media source directories.

Given relative file paths (as reported by ``album check``), resolves all
associated variants by key (image number for iOS, filename stem for std)
and moves or deletes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..common.fs import delete_files, file_ext, move_files
from .store.fs import discover_media_sources
from .store.media_sources import find_files_by_key
from .store.protocol import VID_EXTENSIONS, MediaSource

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


def _is_video(filename: str) -> bool:
    return file_ext(filename) in VID_EXTENSIONS


def _find_matching_files(
    album_dir: Path,
    subdir: str,
    keys: set[str],
    ms: MediaSource,
) -> list[str]:
    """Find files in *album_dir/subdir* matching *keys* using *ms.key_fn*."""
    directory = album_dir / subdir
    if not directory.is_dir():
        return []
    return find_files_by_key(keys, directory, ms.key_fn)


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
        key = ms.key_fn(filename)

        group_key = (ms.name, video)
        groups.setdefault(group_key, set()).add(key)
        ms_by_name[ms.name] = ms

    # Resolve variants across all directories
    result: list[tuple[str, list[str]]] = []
    for (ms_name, video), keys in groups.items():
        ms = ms_by_name[ms_name]
        dirs = ms.video_variant_dirs if video else ms.image_variant_dirs

        for subdir in dirs:
            files = _find_matching_files(album_dir, subdir, keys, ms)
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
                # Also remove parent if it's a nested archive dir (e.g. ios-main/orig-img)
                parent = directory.parent
                if (
                    parent != album_dir
                    and parent.is_dir()
                    and not any(parent.iterdir())
                ):
                    parent.rmdir()


def _check_move_conflicts(
    variants: list[tuple[str, list[str]]],
    dest_album: Path,
    dest_dir_to_ms: dict[str, MediaSource],
) -> list[str]:
    """Check for conflicts in the destination album before moving.

    Returns a sorted list of conflicting file paths, empty if no conflicts.
    """
    conflicts: set[str] = set()
    for subdir, files in variants:
        ms = dest_dir_to_ms.get(subdir)
        if ms is None:
            continue
        keys = {ms.key_fn(f) for f in files}
        for existing in _find_matching_files(dest_album, subdir, keys, ms):
            conflicts.add(f"{subdir}/{existing}")
    return sorted(conflicts)


def move_media(
    source_album: Path,
    dest_album: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """Move media files and all their variants from *source_album* to *dest_album*."""
    variants = resolve_variants(source_album, relative_paths)

    # Fail fast before moving anything if the destination already contains
    # files with the same key.
    dest_media_sources = discover_media_sources(dest_album)
    dest_dir_to_ms = _build_dir_to_media_source(dest_media_sources)
    conflicts = _check_move_conflicts(variants, dest_album, dest_dir_to_ms)

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
        )
        moved.append((subdir, tuple(files)))

    _remove_empty_dirs(source_album, [subdir for subdir, _ in moved], dry_run=dry_run)
    return MediaOpResult(files_by_dir=tuple(moved))


def rm_media(
    album_dir: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """Remove media files and all their variants from *album_dir*."""
    variants = resolve_variants(album_dir, relative_paths)

    removed: list[tuple[str, tuple[str, ...]]] = []
    for subdir, files in variants:
        delete_files(
            album_dir / subdir,
            files,
            dry_run=dry_run,
        )
        removed.append((subdir, tuple(files)))

    _remove_empty_dirs(album_dir, [subdir for subdir, _ in removed], dry_run=dry_run)
    return MediaOpResult(files_by_dir=tuple(removed))


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def media_op_summary(
    verb: str,
    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in files_by_dir)
    if total == 0:
        return f"Done. No files to {verb.lower()}."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in files_by_dir)
    return f"Done. {verb} {total} file(s): {parts}."


def media_op_check_suggestions(album_dirs: list[str]) -> str:
    lines = ["", "Suggested next steps:"]
    lines.extend(f'  photree album check --album-dir "{d}"' for d in album_dirs)
    return "\n".join(lines)
