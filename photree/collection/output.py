"""
Human-readable rendering of collection settings and check issues.

The core reports kinds and fields; this module turns them into messages.
Formatters return unindented lines, the caller indents.
"""

from collections.abc import Callable, Iterable
from pathlib import Path

from photree.album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from photree.collection.check import CollectionCheckIssue, CollectionIssueCode
from photree.collection.id import format_collection_external_id
from photree.collection.store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionStrategy,
    MemberType,
)
from photree.common.fs import display_path
from photree.foundation.layout import PHOTREE_DIR


def format_unreadable_album(album_dir: Path, cwd: Path) -> str:
    """
    Return the warning for an album a collection check could not read.

    Two lines: the problem, and the command that shows why.
    """
    path = display_path(album_dir, cwd)
    return (
        f"warning: cannot read the metadata of album {path}; members it holds "
        "may be reported as not found.\n"
        f"Run 'photree album check --album-dir \"{path}\"' to see why."
    )


def format_invalid_collection_config(
    members: CollectionMembers,
    lifecycle: CollectionLifecycle,
    strategy: CollectionStrategy,
) -> str:
    """Return the message for a members/lifecycle/strategy combination not allowed."""
    return (
        f"invalid combination: members={members.value}, "
        f"lifecycle={lifecycle.value}, strategy={strategy.value}. "
        "See 'photree collection init --help' for valid combinations."
    )


def _safe_fmt(fmt: Callable[[str], str]) -> Callable[[str], str]:
    def _inner(mid: str) -> str:
        try:
            return fmt(mid)
        except ValueError:
            return mid

    return _inner


# An ID that is not a valid UUID is shown as written rather than raising.
_ID_FORMATTERS: dict[MemberType, Callable[[str], str]] = {
    MemberType.ALBUM: _safe_fmt(format_album_external_id),
    MemberType.COLLECTION: _safe_fmt(format_collection_external_id),
    MemberType.IMAGE: _safe_fmt(format_image_external_id),
    MemberType.VIDEO: _safe_fmt(format_video_external_id),
}


def format_member(member_type: MemberType, member_id: str) -> str:
    """Return ``<type> <external ID>``, e.g. ``album album_3K8vJxNm2cYpR7qWz5FhG``."""
    return f"{member_type} {_ID_FORMATTERS[member_type](member_id)}"


def _issue_member(issue: CollectionCheckIssue) -> str:
    match (issue.member_type, issue.member_id):
        case (MemberType() as member_type, str() as member_id):
            return format_member(member_type, member_id)
        case _:
            return "member"


_SMART_MEDIA = "smart collections can only contain albums and collections"


def format_collection_issue(issue: CollectionCheckIssue) -> str:
    """Return the one-line message for a collection check issue."""
    member = _issue_member(issue)
    match issue.code:
        case CollectionIssueCode.NO_METADATA:
            return f"missing {PHOTREE_DIR}/{COLLECTION_YAML}"
        case CollectionIssueCode.INVALID_METADATA:
            return f"invalid {PHOTREE_DIR}/{COLLECTION_YAML}: {issue.reason}"
        case CollectionIssueCode.INVALID_COLLECTION_CONFIG:
            return (
                format_invalid_collection_config(*issue.config)
                if issue.config is not None
                else "invalid combination of members, lifecycle and strategy"
            )
        case (
            CollectionIssueCode.MISSING_ALBUM
            | CollectionIssueCode.MISSING_COLLECTION
            | CollectionIssueCode.MISSING_IMAGE
            | CollectionIssueCode.MISSING_VIDEO
        ):
            return f"{member} not found in gallery"
        case CollectionIssueCode.DATE_NOT_COVERED:
            return (
                f"{member} date {issue.member_date} outside collection range "
                f"{issue.collection_date}"
            )
        case CollectionIssueCode.SMART_HAS_IMAGES:
            return (
                f"smart collection has {issue.count} image member(s) — {_SMART_MEDIA}"
            )
        case CollectionIssueCode.SMART_HAS_VIDEOS:
            return (
                f"smart collection has {issue.count} video member(s) — {_SMART_MEDIA}"
            )
        case CollectionIssueCode.CHAPTER_DATE_OVERLAP:
            return (
                f"chapter date range {issue.collection_date} overlaps with "
                f"chapter '{issue.other_chapter}' ({issue.other_date})"
            )
        case CollectionIssueCode.MEMBERSHIP_CYCLE:
            return f"{member} contains this collection back (membership cycle)"
        case (
            CollectionIssueCode.PRIVATE_SMART_HAS_NON_PRIVATE_ALBUM
            | CollectionIssueCode.PRIVATE_SMART_HAS_NON_PRIVATE_COLLECTION
        ):
            return f"private smart collection contains non-private {member}"
        case (
            CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_ALBUM
            | CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_COLLECTION
        ):
            return f"non-private collection contains private {member}"
        case CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_MEDIA:
            return f"non-private collection contains {member} from private album"


def format_issue_suggestions(
    issues: Iterable[CollectionCheckIssue],
    collection_dir: Path,
    cwd: Path,
) -> list[str]:
    """
    Return the commands that fix *issues*, one unindented line each, without repeats.

    Issue kinds no command fixes (a member missing from the gallery, a
    corrupt metadata file) suggest nothing.
    """
    path = display_path(collection_dir, cwd)
    drop_media = (
        "Run 'photree gallery refresh' to drop the images and videos of "
        "smart collections."
    )
    by_code = {
        CollectionIssueCode.NO_METADATA: (
            f"Run 'photree collection init --collection-dir \"{path}\"' "
            "to initialize the collection."
        ),
        CollectionIssueCode.INVALID_COLLECTION_CONFIG: (
            "Run 'photree collection metadata set --collection-dir "
            f'"{path}" --members <members> --lifecycle <lifecycle> '
            "--strategy <strategy>' with a valid combination."
        ),
        CollectionIssueCode.SMART_HAS_IMAGES: drop_media,
        CollectionIssueCode.SMART_HAS_VIDEOS: drop_media,
    }
    return list(dict.fromkeys(by_code[i.code] for i in issues if i.code in by_code))
