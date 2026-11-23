"""
Output formatting for a check over many albums.

Used by ``albums check`` and ``gallery check``.

Formatters return unindented lines; nested detail lines are indented relative
to their heading with :func:`~photree.common.formatting.indent`, and the call
site decides how deep the whole block sits.

Formatters return Rich markup: every user-derived value (album and media
source names, paths, filenames, issue messages) is escaped with
:func:`~photree.common.formatting.markup_escape` here, so callers print the
result with markup enabled and must not escape it again.
"""

from collections.abc import Callable
from pathlib import Path

from photree.album.naming import BatchNamingResult
from photree.common.formatting import (
    CHECK,
    CROSS,
    indent,
    markup_escape,
)
from photree.common.fs import display_path


def format_batch_naming_issues(result: BatchNamingResult) -> str:
    """Format cross-album naming issues (date collisions)."""
    if result.success:
        return f"{CHECK} no date collisions"
    else:
        return "\n".join(
            [
                f"{CROSS} date collisions: {len(result.date_collisions)} date(s)",
                *(
                    line
                    for album_date, albums in result.date_collisions
                    for line in (
                        indent(f"{album_date}:"),
                        *(indent(markup_escape(album), 2) for album in albums),
                    )
                ),
            ],
        )


def batch_check_summary(passed: int, failed: int, warned: int = 0) -> str:
    """Format the closing line of a batch check with its album counts."""
    parts = [
        f"{passed} album(s) passed",
        *([f"{warned} with warnings"] if warned else []),
        f"{failed} failed",
    ]
    return f"\nDone. {', '.join(parts)}."


def duplicate_ids_report(
    kind: str,
    duplicates: dict[str, list[Path]],
    base: Path,
    format_id: Callable[[str], str],
) -> str:
    """Format duplicate-ID findings. *kind* is ``"album"`` or ``"media"``."""
    return "\n".join(
        "\n".join(
            [
                f"{CROSS} duplicate {kind} id: {format_id(dup_id)}",
                *(indent(markup_escape(display_path(p, base)), 2) for p in paths),
            ],
        )
        for dup_id, paths in duplicates.items()
    )


def no_duplicate_ids_line(kind: str) -> str:
    """Return the success counterpart of :func:`duplicate_ids_report`."""
    return f"{CHECK} no duplicate {kind} ids"


def batch_check_retry_flags(
    *,
    fatal_warnings: bool,
    fatal_sidecar: bool,
    fatal_exif_date_match: bool,
) -> str:
    """
    Reconstruct the flags needed to reproduce a batch check on one album.

    A suggested command that silently drops the caller's flags would not
    reproduce the failure it is suggested for.
    """
    return "".join(
        [
            " --fatal-warnings" if fatal_warnings else "",
            " --fatal-sidecar" if fatal_sidecar else "",
            " --no-fatal-exif-date-match" if not fatal_exif_date_match else "",
        ],
    )
