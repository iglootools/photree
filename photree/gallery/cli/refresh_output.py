"""Text rendering for ``gallery refresh`` results.

Formatters return unindented lines; callers indent them. Paths are rendered
relative to the working directory, and every error carries a copy-pasteable
next step.
"""

from __future__ import annotations

from pathlib import Path

from ...album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from ...collection.id import format_collection_external_id
from ...common.formatting import indent
from ...common.fs import display_path
from ..browsable_refresh import (
    BrowsableRefreshError,
    BrowsableRefreshErrorKind,
    DanglingMember,
    DanglingMemberKind,
)
from ..collection_refresh import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
    CollectionRefreshResult,
)


def _path(path: Path | None, cwd: Path) -> str:
    return str(display_path(path, cwd)) if path is not None else "?"


def _album_check(path: Path | None, cwd: Path) -> str:
    return f"'photree album check --album-dir \"{_path(path, cwd)}\"'"


def _collection_check(path: Path | None, cwd: Path) -> str:
    return f"'photree collection check --dir \"{_path(path, cwd)}\"'"


def format_collection_refresh_error(err: CollectionRefreshError, cwd: Path) -> str:
    """Describe one collection refresh error and how to resolve it."""
    match err.kind:
        case CollectionRefreshErrorKind.ALBUM_NAMING:
            return "\n".join(
                [
                    f"album {_path(err.path, cwd)}: name breaks the naming convention",
                    *(indent(issue.message) for issue in err.naming_issues),
                    f"Rename the album; run {_album_check(err.path, cwd)} for details.",
                ]
            )
        case CollectionRefreshErrorKind.ALBUM_MISSING_METADATA:
            return (
                f"album {_path(err.path, cwd)}: album metadata cannot be read\n"
                f"Run {_album_check(err.path, cwd)} to investigate."
            )
        case CollectionRefreshErrorKind.COLLECTION_UNREADABLE_METADATA:
            return (
                f"collection {_path(err.path, cwd)}: collection metadata cannot "
                f"be read\nRun {_collection_check(err.path, cwd)} to investigate."
            )
        case CollectionRefreshErrorKind.DATE_COLLISION:
            return (
                f"date collision on {err.name}: {', '.join(err.album_names)}\n"
                "Add part numbers to disambiguate; run 'photree gallery check' "
                "for the full report."
            )
        case CollectionRefreshErrorKind.ALBUM_RENAME_CONFLICT:
            return (
                f"album {_path(err.path, cwd)}: cannot sync its title, "
                f"{_path(err.target, cwd)} is already taken\n"
                "Rename one of the two albums, then run 'photree gallery refresh'."
            )
        case CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS:
            source = (
                f"cannot rename {_path(err.path, cwd)}"
                if err.path is not None
                else "cannot create implicit collection"
            )
            return (
                f"{source}: {_path(err.target, cwd)} already exists\n"
                "Move the existing directory away, then run 'photree gallery refresh'."
            )
        case CollectionRefreshErrorKind.SERIES_NAME_CONFLICT:
            return (
                f"implicit collection '{err.name}' is claimed by two separate "
                "runs of the same series on the same dates\n"
                "Give the runs distinct series names, then run "
                "'photree gallery refresh'."
            )


def format_collection_changes(result: CollectionRefreshResult) -> list[str]:
    """One line per collection change (unindented), plus the album renames."""
    changes = [
        *(f"created: {name}" for name in result.created),
        *(f"updated: {name}" for name in result.updated),
        *(f"renamed: {old} -> {new}" for old, new in result.renamed),
        *(f"deleted: {name}" for name in result.deleted),
    ]
    renames = [f"{old} -> {new}" for old, new in result.album_renames]
    return [
        *(changes or ([] if renames else ["no changes"])),
        *(["", "Album title sync:", *renames] if renames else []),
    ]


def format_browsable_error(err: BrowsableRefreshError, cwd: Path) -> str:
    """Describe one browsable refresh error and how to resolve it."""
    match err.kind:
        case BrowsableRefreshErrorKind.REGULAR_FILE:
            return (
                f"browsable/ contains a regular file: {_path(err.path, cwd)}\n"
                "Expected only directories and symlinks. Remove the file (or "
                "browsable/), then run 'photree gallery refresh'."
            )
        case BrowsableRefreshErrorKind.ALBUM_MISSING_METADATA:
            return (
                f"album {_path(err.path, cwd)}: album metadata cannot be read\n"
                f"Run {_album_check(err.path, cwd)} to investigate."
            )
        case BrowsableRefreshErrorKind.ALBUM_UNPARSEABLE_NAME:
            return (
                f"album {_path(err.path, cwd)}: name has no parseable date\n"
                f"Rename the album; run {_album_check(err.path, cwd)} for details."
            )
        case BrowsableRefreshErrorKind.COLLECTION_UNREADABLE_METADATA:
            return (
                f"collection {_path(err.path, cwd)}: collection metadata cannot "
                f"be read\nRun {_collection_check(err.path, cwd)} to investigate."
            )
        case BrowsableRefreshErrorKind.CYCLE:
            collection_id = (
                format_collection_external_id(err.collection_id)
                if err.collection_id is not None
                else "?"
            )
            return (
                f"cycle detected: collection {_path(err.path, cwd)} "
                f"({collection_id}) contains itself through its members\n"
                f"Run {_collection_check(err.path, cwd)} to investigate."
            )


def _member_external_id(member: DanglingMember) -> str:
    match member.kind:
        case DanglingMemberKind.ALBUM:
            return format_album_external_id(member.member_id)
        case DanglingMemberKind.COLLECTION:
            return format_collection_external_id(member.member_id)
        case DanglingMemberKind.IMAGE:
            return format_image_external_id(member.member_id)
        case DanglingMemberKind.VIDEO:
            return format_video_external_id(member.member_id)


def format_dangling_members(members: tuple[DanglingMember, ...], cwd: Path) -> str:
    """Report collection members that resolve to nothing (skipped when rendering)."""
    collections = list(dict.fromkeys(m.collection_path for m in members))
    return "\n".join(
        [
            f"{len(members)} collection member(s) not found in the gallery (skipped):",
            *(
                indent(
                    f"{_path(m.collection_path, cwd)}: {m.kind} "
                    f"{_member_external_id(m)}"
                )
                for m in members
            ),
            "To investigate, run:",
            *(indent(_collection_check(c, cwd)) for c in collections),
        ]
    )
