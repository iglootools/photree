from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ....common.fs import file_ext, list_files
from ...formats import IOS_SIDECAR_EXTENSIONS
from ...store.file_matching import ios_is_media
from ...store.media_source import ios_img_number


class SidecarIssueKind(StrEnum):
    # An original HEIC without its IMG_XXXX.AAE (informational).
    MISSING_SIDECAR = "missing-sidecar"
    # An edited file without its IMG_OXXXX.AAE (informational).
    MISSING_EDIT_SIDECAR = "missing-edit-sidecar"
    # An AAE in orig with no original media of that number (error).
    ORPHAN_SIDECAR = "orphan-sidecar"
    # An IMG_O*.AAE in edit with no edited media of that number (error).
    ORPHAN_EDIT_SIDECAR = "orphan-edit-sidecar"


@dataclass(frozen=True)
class SidecarIssue:
    """A sidecar problem for *file* in *directory* (a directory name)."""

    file: str
    directory: str
    kind: SidecarIssueKind


@dataclass(frozen=True)
class SidecarCheck:
    missing_sidecars: tuple[SidecarIssue, ...]
    orphan_sidecars: tuple[SidecarIssue, ...]


def _missing_sidecars(
    orig_dir: Path, orig_files: set[str], edit_dir: Path, edit_files: set[str]
) -> tuple[SidecarIssue, ...]:
    return (
        *[
            SidecarIssue(f, orig_dir.name, SidecarIssueKind.MISSING_SIDECAR)
            for f in sorted(orig_files)
            if file_ext(f) == ".heic"
            and f"IMG_{ios_img_number(f)}.AAE" not in orig_files
        ],
        *[
            SidecarIssue(f, edit_dir.name, SidecarIssueKind.MISSING_EDIT_SIDECAR)
            for f in sorted(edit_files)
            if ios_is_media(f)
            and f.upper().startswith("IMG_E")
            and f"IMG_O{ios_img_number(f)}.AAE" not in edit_files
        ],
    )


def _orphan_sidecars(
    orig_dir: Path, orig_files: set[str], edit_dir: Path, edit_files: set[str]
) -> tuple[SidecarIssue, ...]:
    orig_media_numbers = {ios_img_number(f) for f in orig_files if ios_is_media(f)}
    edit_media_numbers = {
        ios_img_number(f)
        for f in edit_files
        if ios_is_media(f) and f.upper().startswith("IMG_E")
    }
    return (
        *[
            SidecarIssue(f, orig_dir.name, SidecarIssueKind.ORPHAN_SIDECAR)
            for f in sorted(orig_files)
            if file_ext(f) in IOS_SIDECAR_EXTENSIONS
            and ios_img_number(f) not in orig_media_numbers
        ],
        *[
            SidecarIssue(f, edit_dir.name, SidecarIssueKind.ORPHAN_EDIT_SIDECAR)
            for f in sorted(edit_files)
            if file_ext(f) in IOS_SIDECAR_EXTENSIONS
            and f.upper().startswith("IMG_O")
            and ios_img_number(f) not in edit_media_numbers
        ],
    )


def check_sidecars(
    orig_dir: Path,
    edit_dir: Path,
) -> SidecarCheck:
    orig_files = set(list_files(orig_dir))
    edit_files = set(list_files(edit_dir))
    return SidecarCheck(
        missing_sidecars=_missing_sidecars(orig_dir, orig_files, edit_dir, edit_files),
        orphan_sidecars=_orphan_sidecars(orig_dir, orig_files, edit_dir, edit_files),
    )
