"""User-facing messages for gallery import.

Pure formatting helpers that return rich-markup strings; the CLI layer is
responsible for printing them (see ``cli/ops.py``).
"""

from __future__ import annotations

from pathlib import Path

from ..album.id import format_album_external_id
from ..album.naming import NamingIssue
from ..common.formatting import CROSS, WARNING
from ..common.fs import display_path
from .import_plan import AlbumPlan, ClobberConflict, GalleryImportPlan, SourceDuplicate


def _naming_block(album: Path, issues: tuple[NamingIssue, ...], cwd: Path) -> list[str]:
    return [
        f"{CROSS} {display_path(album, cwd)} — naming: {len(issues)} issue(s)",
        *(f"    {issue.message}" for issue in issues),
    ]


def _structure_block(album: Path, cwd: Path) -> list[str]:
    return [
        f"{CROSS} {display_path(album, cwd)} — no media source found "
        "(expected an ios-* or std-* archive directory)"
    ]


def _collision_block(date_str: str, names: tuple[str, ...]) -> list[str]:
    return [
        f"{CROSS} date collision on {date_str} (add part numbers to disambiguate):",
        *(f"    {name}" for name in names),
    ]


def _duplicate_id_block(dup: SourceDuplicate, cwd: Path) -> list[str]:
    return [
        f"{CROSS} duplicate album ID {format_album_external_id(dup.album_id)} "
        "among source albums:",
        *(f"    {display_path(p, cwd)}" for p in dup.paths),
    ]


def _clobber_block(conflict: ClobberConflict, cwd: Path) -> list[str]:
    return [
        f"{CROSS} {display_path(conflict.source, cwd)} — a different album "
        f"already occupies {display_path(conflict.existing, cwd)}",
        f"    source id:   {format_album_external_id(conflict.source_id)}",
        f"    existing id: {format_album_external_id(conflict.existing_id)}",
        "    Rename the source album before importing.",
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
                f"{WARNING} {display_path(plan.existing or plan.target, cwd)}"
                for plan in plans
            ),
        ]
    )
