"""
Rendering of media operations (``rm-media``, ``mv-media``) for the CLI.

Turns :class:`~photree.album.media.MediaOpError` and
:class:`~photree.album.media.MediaOpResult` data into the lines the commands
print, with paths relative to the working directory.
"""

from pathlib import Path

from photree.album.media import MediaOpError, MediaOpErrorKind
from photree.common.formatting import indent
from photree.common.fs import display_path

_MAX_LISTED_CONFLICTS = 10


def format_media_op_error(exc: MediaOpError, cwd: Path) -> str:
    """Render a :class:`MediaOpError` for the CLI, with display paths."""
    album = display_path(exc.album_dir, cwd)
    match exc.kind:
        case MediaOpErrorKind.NO_MEDIA_SOURCES:
            return f"No media sources found in {album}."
        case MediaOpErrorKind.PATH_WITHOUT_DIRECTORY:
            return (
                f'"{exc.rel_path}" must be a relative path with a directory'
                " (e.g. main-jpg/IMG_E3219.jpg)."
            )
        case MediaOpErrorKind.UNKNOWN_DIRECTORY:
            return (
                f'Directory "{exc.subdir}" does not match any media source in {album}.'
            )
        case MediaOpErrorKind.NO_MATCHING_FILE:
            return "\n".join(
                [
                    f"No file in {album} matches these requested path(s):",
                    *(indent(p) for p in exc.rel_paths),
                    "Nothing was changed.",
                ],
            )
        case MediaOpErrorKind.MOVE_CONFLICT:
            return _format_move_conflicts(exc.conflicts, album)
        case MediaOpErrorKind.MEDIA_SOURCE_TYPE_MISMATCH:
            return (
                f"{album} has media source(s) {', '.join(exc.media_sources)}"
                " of the other type (ios vs std) than in the source album."
                " Moving would put ios-<name>/ and std-<name>/ archives side"
                " by side. Rename the media source in one of the two albums"
                " first."
            )


def _format_move_conflicts(conflicts: tuple[str, ...], album: Path) -> str:
    shown = conflicts[:_MAX_LISTED_CONFLICTS]
    hidden = len(conflicts) - len(shown)
    return "\n".join(
        [
            f"Move would conflict with {len(conflicts)} existing file(s) in {album}:",
            *(indent(c) for c in shown),
            *([indent(f"... and {hidden} more")] if hidden > 0 else []),
            "Use a different media source to avoid conflicts.",
        ],
    )


def format_media_op_summary(
    verb: str,
    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    dry_run: bool = False,
) -> str:
    """Summarize a media operation; *verb* is its infinitive ("move", "remove")."""
    total = sum(len(files) for _, files in files_by_dir)
    if total == 0:
        return f"No files to {verb}." if dry_run else f"Done. No files to {verb}."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in files_by_dir)
    return (
        f"Would {verb} {total} file(s): {parts}."
        if dry_run
        else f"Done. {verb.capitalize()}d {total} file(s): {parts}."
    )


def format_media_op_check_suggestions(album_dirs: list[str]) -> str:
    """Return the lines suggesting an ``album check`` of each of *album_dirs*."""
    return "\n".join(
        [
            "",
            "Suggested next steps:",
            *(indent(f'photree album check --album-dir "{d}"') for d in album_dirs),
        ],
    )
