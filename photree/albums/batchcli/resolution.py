"""
Album list resolution and display names for batch commands.

Turns the mutually exclusive ``--dir`` / ``--album-dir`` options into an
album list; used by both ``albums`` and ``gallery`` CLI commands.
"""

from collections.abc import Callable
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from photree.album import check as album_check
from photree.album.store.album_discovery import discover_potential_albums
from photree.clihelpers.usage import mutually_exclusive_error
from photree.common.fs import display_path


def display_name(album_dir: Path, base_dir: Path | None, cwd: Path) -> str:
    """Human-readable album name relative to *base_dir* or *cwd*."""
    if base_dir is not None:
        return str(album_dir.relative_to(base_dir))

    return str(display_path(album_dir, cwd))


def make_display_fn(display_base: Path | None, cwd: Path) -> Callable[[Path], str]:
    """Return a function giving an album's display name, as :func:`display_name`."""
    return lambda album_dir: display_name(album_dir, display_base, cwd)


def resolve_check_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    *,
    cwd: Path,
) -> tuple[list[Path], Path | None]:
    """
    Resolve album list for check commands (all album types).

    Uses :func:`discover_albums` which detects iOS albums, ``.album``
    sentinels, and leaf directories.
    """
    return _resolve_batch_albums_with(
        base_dir,
        album_dirs,
        album_check.discover_albums,
        cwd=cwd,
    )


def resolve_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    *,
    cwd: Path,
) -> tuple[list[Path], Path | None]:
    """
    Resolve album list for archive-based commands.

    Uses :func:`discover_archive_albums` which finds albums with iOS
    (``ios-*/``) or std (``std-*/``) archive directories.
    """
    return _resolve_batch_albums_with(
        base_dir,
        album_dirs,
        album_check.discover_archive_albums,
        cwd=cwd,
    )


def resolve_init_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    *,
    cwd: Path,
) -> tuple[list[Path], Path | None]:
    """
    Resolve album list for init commands.

    Uses :func:`discover_potential_albums` which finds directories with
    media sources regardless of whether ``.photree/album.yaml`` exists.
    The skipped (non-album) directories are discarded — ``init`` is
    indifferent to them.
    """
    return _resolve_batch_albums_with(
        base_dir,
        album_dirs,
        lambda d: discover_potential_albums(d)[0],
        cwd=cwd,
    )


def _resolve_batch_albums_with(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    discover_fn: Callable[[Path], list[Path]],
    *,
    cwd: Path,
) -> tuple[list[Path], Path | None]:
    """
    Resolve album list from mutually exclusive --dir / --album-dir options.

    Returns ``(albums, display_base)`` where *display_base* is the base
    directory when --dir was used (for relative display names), or ``None``
    when --album-dir was used (display names are CWD-relative).
    """
    if base_dir is not None and album_dirs is not None:
        raise mutually_exclusive_error(
            ("--dir", "--album-dir"),
            advice=(
                "scan a base directory with --dir, or list albums "
                "with --album-dir (repeatable)"
            ),
        )

    if album_dirs is not None:
        return (album_dirs, None)

    resolved_base = base_dir if base_dir is not None else cwd
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Resolving album list...", total=None)
        albums = discover_fn(resolved_base)
    return (albums, resolved_base)
