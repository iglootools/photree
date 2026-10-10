"""User-facing messages for the exporter."""

from __future__ import annotations

import shlex
from pathlib import Path

from ...common.formatting import indent
from ...common.fs import display_path
from ...foundation.layout import SHARE_SENTINEL
from .settings import ExportSettingsError, ExportSettingsErrorKind


def format_export_settings_error(
    exc: ExportSettingsError, cwd: Path, command: str
) -> str:
    """Plain text (print with ``markup=False``) with a copy-pasteable fix.

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
            share_dir = display_path(exc.share_dir or Path("."), cwd)
            sentinel = shlex.quote(str(share_dir / SHARE_SENTINEL))
            return "\n".join(
                [
                    f"Share directory has no {SHARE_SENTINEL} sentinel file: {share_dir}",
                    "",
                    (
                        "To initialize a share directory, ensure the volume is"
                        " mounted and create the sentinel file:"
                    ),
                    indent(f"touch {sentinel}"),
                ]
            )


def export_summary(album_name: str, files_copied: int, album_type: str) -> str:
    return f"Done. Exported {album_name} ({album_type}): {files_copied} file(s)."


def batch_export_summary(exported: int, failed: int) -> str:
    return f"\nDone. {exported} album(s) exported, {failed} failed."
