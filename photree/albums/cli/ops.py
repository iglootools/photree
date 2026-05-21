"""Shared helpers for albums CLI commands.

Album resolution and display utilities used by both ``albums`` and
``gallery`` CLI commands.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from ...album import check as album_check
from ...album.store.album_discovery import discover_potential_albums
from ...common.fs import display_path


def display_name(album_dir: Path, base_dir: Path | None, cwd: Path) -> str:
    """Human-readable album name relative to *base_dir* or *cwd*."""
    if base_dir is not None:
        return str(album_dir.relative_to(base_dir))

    return str(display_path(album_dir, cwd))


def make_display_fn(display_base: Path | None, cwd: Path) -> Callable[[Path], str]:
    """Create a display function for album paths."""
    return lambda album_dir: display_name(album_dir, display_base, cwd)


# ---------------------------------------------------------------------------
# Album resolution helpers
# ---------------------------------------------------------------------------


def resolve_check_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for check commands (all album types).

    Uses :func:`discover_albums` which detects iOS albums, ``.album``
    sentinels, and leaf directories.
    """
    return _resolve_batch_albums_with(base_dir, album_dirs, album_check.discover_albums)


def resolve_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for archive-based commands.

    Uses :func:`discover_archive_albums` which finds albums with iOS
    (``ios-*/``) or std (``std-*/``) archive directories.
    """
    return _resolve_batch_albums_with(
        base_dir, album_dirs, album_check.discover_archive_albums
    )


def resolve_init_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for init commands.

    Uses :func:`discover_potential_albums` which finds directories with
    media sources regardless of whether ``.photree/album.yaml`` exists.
    """
    return _resolve_batch_albums_with(base_dir, album_dirs, discover_potential_albums)


def _resolve_batch_albums_with(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    discover_fn: Callable[[Path], list[Path]],
) -> tuple[list[Path], Path | None]:
    """Resolve album list from mutually exclusive --dir / --album-dir options.

    Returns ``(albums, display_base)`` where *display_base* is the base
    directory when --dir was used (for relative display names), or ``None``
    when --album-dir was used (display names are CWD-relative).
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    if base_dir is not None and album_dirs is not None:
        typer.echo(
            "--dir and --album-dir are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    if album_dirs is not None:
        return (album_dirs, None)

    # --dir mode (explicit or default)
    resolved_base = base_dir if base_dir is not None else Path(".").resolve()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Resolving album list...", total=None)
        albums = discover_fn(resolved_base)
    return (albums, resolved_base)
