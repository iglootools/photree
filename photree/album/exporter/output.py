"""Text the CLI prints for album exports: settings errors and summaries."""

import shlex
from pathlib import Path

from photree.album.exporter.settings import ExportSettingsError, ExportSettingsErrorKind
from photree.common.formatting import indent
from photree.common.fs import display_path
from photree.foundation.layout import SHARE_SENTINEL


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
) -> str:
    """
    Return the closing line for one album export: its name, type and file counts.

    The stale files removed are mentioned only when there were some.
    """
    removed = f", {files_removed} stale file(s) removed" if files_removed else ""
    return (
        f"Done. Exported {album_name} ({album_type}): {files_copied} file(s){removed}."
    )


def batch_export_summary(exported: int, failed: int) -> str:
    """Return the closing line for a batch export, preceded by a blank line."""
    return f"\nDone. {exported} album(s) exported, {failed} failed."
