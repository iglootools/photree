"""User-facing messages for gallery import.

Pure formatting helpers that return rich-markup strings, with user text
(paths, album names, issue messages) escaped via ``markup_escape``; the CLI
layer is responsible for printing them (see ``cli/ops.py``). The import
failure helpers at the bottom return plain text instead.
"""

from __future__ import annotations

from pathlib import Path

from ..album.faces.failures import format_face_failures
from ..album.id import format_album_external_id
from ..album.naming import NamingIssue
from ..common.formatting import CROSS, WARNING, indent, markup_escape
from ..common.fs import display_path
from .cmd_handler.importer import AlbumImportFailure
from .import_plan import AlbumPlan, ClobberConflict, GalleryImportPlan, SourceDuplicate
from .importer import TargetExistsError


def _shown(path: Path, cwd: Path) -> str:
    """*path* relative to *cwd*, escaped for Rich markup."""
    return markup_escape(display_path(path, cwd))


def _naming_block(album: Path, issues: tuple[NamingIssue, ...], cwd: Path) -> list[str]:
    return [
        f"{CROSS} {_shown(album, cwd)} — naming: {len(issues)} issue(s)",
        *(indent(markup_escape(issue.message), 2) for issue in issues),
    ]


def _structure_block(album: Path, cwd: Path) -> list[str]:
    return [
        (
            f"{CROSS} {_shown(album, cwd)} — no media source found "
            "(expected an ios-* or std-* archive directory)"
        )
    ]


def _collision_block(date_str: str, names: tuple[str, ...]) -> list[str]:
    return [
        f"{CROSS} date collision on {date_str} (add part numbers to disambiguate):",
        *(indent(markup_escape(name), 2) for name in names),
    ]


def _duplicate_id_block(dup: SourceDuplicate, cwd: Path) -> list[str]:
    return [
        (
            f"{CROSS} duplicate album ID {format_album_external_id(dup.album_id)} "
            "among source albums:"
        ),
        *(indent(_shown(p, cwd), 2) for p in dup.paths),
    ]


def _clobber_block(conflict: ClobberConflict, cwd: Path) -> list[str]:
    return [
        (
            f"{CROSS} {_shown(conflict.source, cwd)} — a different album "
            f"already occupies {_shown(conflict.existing, cwd)}"
        ),
        *(
            indent(line, 2)
            for line in (
                f"source id:   {format_album_external_id(conflict.source_id)}",
                f"existing id: {format_album_external_id(conflict.existing_id)}",
                "Rename the source album before importing.",
            )
        ),
    ]


def format_import_errors(plan: GalleryImportPlan, cwd: Path) -> str:
    """Format every pre-import validation error as a single block."""
    blocks = [
        *(_naming_block(album, issues, cwd) for album, issues in plan.naming_errors),
        *(_structure_block(album, cwd) for album in plan.structure_errors),
        *(_collision_block(d, names) for d, names in plan.date_collisions),
        *(_duplicate_id_block(dup, cwd) for dup in plan.source_duplicate_ids),
        *(_clobber_block(conflict, cwd) for conflict in plan.clobber_conflicts),
    ]
    return "\n".join(line for block in blocks for line in block)


def format_skipped(plans: list[AlbumPlan], cwd: Path) -> str:
    """Format the already-imported albums that were skipped."""
    return "\n".join(
        [
            "Skipped (already imported — use --reimport to replace):",
            *(
                f"{WARNING} {_shown(plan.existing or plan.target, cwd)}"
                for plan in plans
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Import execution failures
# ---------------------------------------------------------------------------


def format_import_error(exc: ValueError | OSError, cwd: Path) -> str:
    """Describe an import that raised, with paths relative to *cwd*.

    Plain text (print with ``markup=False``): it also feeds progress-bar
    labels, which escape it themselves.
    """
    match exc:
        case TargetExistsError():
            return (
                f"Target already exists: {display_path(exc.target, cwd)} — an "
                "album with the same name is already in the gallery."
            )
        case OSError(filename=str() | Path() as filename):
            return f"{exc.strerror or type(exc).__name__}: " + str(
                display_path(Path(filename), cwd)
            )
        case _:
            return str(exc)


def format_import_failure_labels(
    failure: AlbumImportFailure, cwd: Path
) -> tuple[str, ...]:
    """One label per reason an album of a batch did not import cleanly (plain text)."""
    return (
        *([format_import_error(failure.error, cwd)] if failure.error else []),
        *(
            f"{source}/{jpeg.filename}: {jpeg.reason}"
            for source, jpeg in failure.jpeg_failures
        ),
        *format_face_failures(failure.face_failures),
    )
