"""Human-readable rendering of collection import errors and results.

The importer reports structured data (kinds + fields); this module turns it
into messages. Formatters return unindented lines — the caller indents.
"""

from __future__ import annotations

from pathlib import Path

from ...common.fs import display_path
from .import_members import (
    CollectionImportError,
    CollectionImportErrorKind,
    CollectionImportResult,
)
from .resolve import (
    ResolutionError,
    ResolutionErrorKind,
    ResolutionWarning,
    ResolvedMembers,
)
from .selection import SELECTION_CSV, SELECTION_DIR, SelectionError, SelectionErrorKind


def format_import_error(exc: CollectionImportError, cwd: Path) -> str:
    """Problem description plus a copy-pasteable suggestion."""
    path = display_path(exc.collection_dir, cwd)
    to_manual = (
        f'Run \'photree collection metadata set --collection-dir "{path}" '
        "--members manual --lifecycle explicit --strategy import' to convert it first."
    )
    match exc.kind:
        case CollectionImportErrorKind.NO_METADATA:
            return (
                f"No collection metadata found in {path}\n"
                f"Run 'photree collection init --collection-dir \"{path}\"' "
                "to initialize."
            )
        case CollectionImportErrorKind.IMPLICIT_COLLECTION:
            return (
                f"Cannot import into implicit collection {path}: members are "
                "managed by 'photree gallery refresh' via album series detection.\n"
                f"{to_manual}"
            )
        case CollectionImportErrorKind.SMART_COLLECTION:
            return (
                f"Cannot import into smart collection {path}: members are managed "
                f"automatically by 'photree gallery refresh'.\n{to_manual}"
            )
        case CollectionImportErrorKind.NO_SELECTION:
            return (
                f"No selection entries found in {path}: add files to "
                f"{SELECTION_DIR}/ or rows to {SELECTION_CSV}."
            )


def format_resolution_error(error: ResolutionError) -> str:
    match error.kind:
        case ResolutionErrorKind.NOT_FOUND:
            reason = "not found in gallery"
        case ResolutionErrorKind.AMBIGUOUS:
            hint = (
                " — provide a date hint to disambiguate"
                if error.date_hint_missing
                else ""
            )
            reason = (
                f"ambiguous: matches {error.match_count} items "
                f"({error.unique_count} unique){hint}"
            )
        case ResolutionErrorKind.DUPLICATE:
            reason = (
                f"duplicate: same item already referenced by '{error.duplicate_of}'"
            )
    return f"[{error.entry}] {reason}"


def format_resolution_warning(warning: ResolutionWarning) -> str:
    return (
        f"warning: [{warning.entry}] date hint {warning.date_hint.isoformat()} "
        f"does not match album date {warning.album_date}"
    )


def format_selection_error(error: SelectionError, cwd: Path) -> str:
    location = f"{display_path(error.csv_path, cwd)}:{error.line}"
    match error.kind:
        case SelectionErrorKind.INVALID_DATE:
            return (
                f"{location}: [{error.entry}] invalid date '{error.value}' "
                "(expected YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, "
                "or YYYY-MM-DDTHH:MM:SS±HHMM)"
            )


def format_result_errors(result: CollectionImportResult, cwd: Path) -> list[str]:
    """Every reason the import failed, one unindented line each."""
    return [
        *(format_selection_error(e, cwd) for e in result.selection_errors),
        *(format_resolution_error(e) for e in result.errors),
    ]


def format_member_counts(members: ResolvedMembers) -> list[str]:
    """Non-zero member counts, one unindented line each."""
    return [
        f"{label}: {len(ids)}"
        for label, ids in (
            ("albums", members.albums),
            ("collections", members.collections),
            ("images", members.images),
            ("videos", members.videos),
        )
        if ids
    ]
