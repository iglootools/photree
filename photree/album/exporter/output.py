"""Text the CLI prints for album exports: errors and summaries."""

import shlex
from collections.abc import Sequence
from pathlib import Path

from photree.album.exporter.batch import ExportFailure
from photree.album.exporter.settings import (
    ExportSettingsError,
    ExportSettingsErrorKind,
    ResolvedExportSettings,
)
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path
from photree.foundation.layout import SHARE_SENTINEL
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout


def format_export_settings_error(
    exc: ExportSettingsError,
    cwd: Path,
    command: str,
) -> str:
    """
    Plain text (print with ``markup=False``) with a copy-pasteable fix.

    *command* is the export command that failed, e.g. ``album export``.
    """
    match exc.kind:
        case ExportSettingsErrorKind.UNKNOWN_PROFILE:
            available = ", ".join(exc.available_profiles) or "(none)"
            return (
                f'Unknown profile "{exc.profile}". Available profiles: {available}\n'
                f"Run 'photree {command} --help' for the export options."
            )
        case ExportSettingsErrorKind.NO_SHARE_DIR:
            return (
                "No --share-dir specified and no profile selected.\n"
                f"Pass --share-dir or --profile; run 'photree {command} --help'"
                " for the export options."
            )
        case ExportSettingsErrorKind.ALBUMS_LAYOUT_NEEDS_ALL:
            layout = exc.album_layout.value if exc.album_layout else "?"
            return (
                'The "albums" share layout requires --album-layout=all, '
                f"but got --album-layout={layout}.\n"
                f"Run 'photree {command} --help' for the export options."
            )
        case ExportSettingsErrorKind.MISSING_SENTINEL:
            share_dir = display_path(exc.share_dir or Path(), cwd)
            sentinel = shlex.quote(str(share_dir / SHARE_SENTINEL))
            return "\n".join(
                [
                    (
                        f"Share directory has no {SHARE_SENTINEL} "
                        f"sentinel file: {share_dir}"
                    ),
                    "",
                    (
                        "To initialize a share directory, ensure the volume is"
                        " mounted and create the sentinel file:"
                    ),
                    indent(f"touch {sentinel}"),
                ],
            )


def export_summary(
    album_name: str,
    album_type: str,
    *,
    files_copied: int,
    files_removed: int,
    target: Path,
    dry_run: bool = False,
) -> str:
    """
    Return the closing line for one album export: its name, type and file counts.

    The stale files removed are mentioned only when there were some. A dry run
    also names *target*, the directory the album would be exported to (shown
    as given: the caller makes it relative to the cwd).
    """
    if dry_run:
        removed = f", {files_removed} stale file(s) to remove" if files_removed else ""
        return format_dry_run(
            f"Would export {album_name} ({album_type}) to {target}:"
            f" {files_copied} file(s){removed}.",
            dry_run=True,
        )
    else:
        removed = f", {files_removed} stale file(s) removed" if files_removed else ""
        return (
            f"Done. Exported {album_name} ({album_type}):"
            f" {files_copied} file(s){removed}."
        )


def batch_export_summary(exported: int, failed: int, *, dry_run: bool = False) -> str:
    """Return the closing line for a batch export, preceded by a blank line."""
    return (
        format_dry_run(
            f"\n{exported} album(s) would be exported, {failed} failed.",
            dry_run=True,
        )
        if dry_run
        else f"\nDone. {exported} album(s) exported, {failed} failed."
    )


def format_batch_export_failures(failed: Sequence[ExportFailure], cwd: Path) -> str:
    """
    Plain text (print with ``markup=False``) listing each failed album and why.

    Followed by the ``album export`` command that reruns each one alone.
    """
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                indent(f"{display_path(album_dir, cwd)}\n{indent(error)}")
                for album_dir, error in failed
            ),
            "\nTo investigate failures:",
            *(
                indent(
                    "photree album export --album-dir "
                    f'"{display_path(album_dir, cwd)}"',
                )
                for album_dir, _ in failed
            ),
        ],
    )


def _os_error_reason(exc: OSError, cwd: Path) -> str:
    """Return *exc*'s reason, naming the file it concerns relative to *cwd*."""
    match exc.strerror, exc.filename:
        case str() as reason, str() | Path() as filename:
            return f"{reason}: {display_path(Path(filename), cwd)}"
        case str() as reason, _:
            return reason
        case _:
            return str(exc)


def format_export_failure(
    album_dir: Path,
    exc: OSError,
    cwd: Path,
    settings: ResolvedExportSettings,
) -> str:
    """
    Plain text (print with ``markup=False``) for an export the filesystem refused.

    When the export links files (the ``all`` layout), the fix suggested is
    the same export with copies, since a share on exFAT, SMB or a cloud
    folder may refuse links; otherwise it is to check the share itself.
    """
    album = display_path(album_dir, cwd)
    problem = f'Could not export "{album}": {_os_error_reason(exc, cwd)}.'
    links = {LinkMode.HARDLINK: "hard links", LinkMode.SYMLINK: "symbolic links"}
    match settings.album_layout, links.get(settings.link_mode):
        case AlbumShareLayout.ALL, str() as kind:
            command = shlex.join(
                [
                    "photree",
                    "album",
                    "export",
                    "--album-dir",
                    str(album),
                    "--share-dir",
                    str(display_path(settings.share_dir, cwd)),
                    "--share-layout",
                    settings.share_layout.value,
                    "--album-layout",
                    settings.album_layout.value,
                    "--link-mode",
                    LinkMode.COPY.value,
                ],
            )
            return "\n".join(
                [
                    problem,
                    f"If the share does not support {kind}, export with copies:",
                    indent(command),
                ],
            )
        case _:
            return (
                f"{problem}\nCheck that the share is mounted, writable and has"
                " free space, then run the export again."
            )
