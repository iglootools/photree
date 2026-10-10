"""Directory resolution helpers shared by every command surface.

``resolve_gallery_or_exit`` lives here rather than in ``gallery/cli/ops.py``
because ``collection`` and ``collections`` commands need it too, and importing
it from ``gallery`` made those packages depend on ``gallery`` — which depends
on them back. It is a generic CLI concern (turn a resolution failure into a
clean exit), not a gallery one.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..common.fs import display_path
from ..fsprotocol import (
    GALLERY_YAML,
    PHOTREE_DIR,
    GalleryNotFoundError,
    InvalidMetadataError,
    resolve_gallery_dir,
)
from .console import err_console


def format_gallery_not_found(exc: GalleryNotFoundError, cwd: Path) -> str:
    """Render a :class:`GalleryNotFoundError` with relative paths and a fix."""
    match exc.explicit:
        case None:
            return (
                f"No gallery metadata ({PHOTREE_DIR}/{GALLERY_YAML}) found in "
                f"{display_path(exc.searched_from, cwd)} or its parent directories.\n"
                "Run 'photree gallery init' in the gallery root, or use --gallery-dir."
            )
        case explicit:
            yaml_path = display_path(explicit / PHOTREE_DIR / GALLERY_YAML, cwd)
            return (
                f"No gallery metadata found at {yaml_path}.\n"
                f"Run 'photree gallery init --gallery-dir \"{display_path(explicit, cwd)}\"'"
                " to initialize the gallery."
            )


def format_invalid_metadata(exc: InvalidMetadataError, cwd: Path) -> str:
    """Render an :class:`InvalidMetadataError` with a relative path and a fix."""
    return (
        f"Invalid metadata in {display_path(exc.path, cwd)}: {exc.reason}\n"
        "Restore the file from a backup or fix its content; photree does not "
        "regenerate it, because a fresh file would carry fresh IDs."
    )


def resolve_gallery_or_exit(gallery_dir: Path | None) -> Path:
    """Resolve gallery directory or exit with a clear error."""
    try:
        return resolve_gallery_dir(gallery_dir)
    except GalleryNotFoundError as exc:
        err_console.print(format_gallery_not_found(exc, Path.cwd()), markup=False)
        raise typer.Exit(code=1) from exc
