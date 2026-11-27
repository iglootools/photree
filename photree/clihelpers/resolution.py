"""
Directory resolution helpers shared by every command surface.

``resolve_gallery_or_exit`` lives here rather than in ``gallery/cli/ops.py``
because ``collection`` and ``collections`` commands need it too, and importing
it from ``gallery`` made those packages depend on ``gallery`` — which depends
on them back. It is a generic CLI concern (turn a resolution failure into a
clean exit), not a gallery one.
"""

from pathlib import Path

import typer

from photree.clihelpers.console import err_console
from photree.common.fs import display_path
from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    GalleryNotFoundError,
    resolve_gallery_dir,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import InvalidMetadataError


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
                "Run 'photree gallery init --gallery-dir "
                f'"{display_path(explicit, cwd)}"\' to initialize the gallery.'
            )


def format_gallery_flag(gallery_dir: Path, cwd: Path) -> str:
    """
    Return the ``--gallery-dir`` flag a suggested command needs, with a leading space.

    Empty when *cwd* is inside *gallery_dir*: the command run from there finds
    the gallery itself. Otherwise the copied command would search from *cwd*
    and fail, so the flag names the gallery, relative to *cwd* when possible.
    """
    return (
        ""
        if cwd.is_relative_to(gallery_dir)
        else f' --gallery-dir "{display_path(gallery_dir, cwd)}"'
    )


def format_invalid_metadata(exc: InvalidMetadataError, cwd: Path) -> str:
    """Render an :class:`InvalidMetadataError` with a relative path and a fix."""
    fix = (
        _derived_cache_fix(exc.path, cwd)
        if exc.derived
        else "Restore the file from a backup or fix its content; photree does not "
        "regenerate it, because a fresh file would carry fresh IDs."
    )
    return f"Invalid metadata in {display_path(exc.path, cwd)}: {exc.reason}\n{fix}"


def _derived_cache_fix(path: Path, cwd: Path) -> str:
    """
    Suggest rebuilding a derived cache, targeting the album that holds *path*.

    The album is the directory holding the ``.photree/`` the cache lives in;
    the suggested command names it, so it does not refresh whatever
    directory the user happens to be in.
    """
    album_dir = next((p.parent for p in path.parents if p.name == PHOTREE_DIR), None)
    refresh = (
        "photree album refresh"
        if album_dir is None
        else f'photree album refresh --album-dir "{display_path(album_dir, cwd)}"'
    )
    return (
        "This cache is derived from the album's files: delete it, or force its "
        f"refresh ('{refresh} --refresh-exif-cache' for the EXIF cache, "
        f"'{refresh} --redetect-faces' for the face cache), and photree rebuilds it."
    )


def resolve_gallery_or_exit(
    gallery_dir: Path | None,
    *,
    cwd: Path,
) -> Path:
    """
    Return the gallery root: *gallery_dir*, or the nearest one above *cwd*.

    Prints why and exits 1 when no gallery metadata is found.
    """
    try:
        return resolve_gallery_dir(gallery_dir, start_dir=cwd)
    except GalleryNotFoundError as exc:
        err_console.print(format_gallery_not_found(exc, cwd), markup=False)
        raise typer.Exit(code=1) from exc
