"""Import photos from macOS Image Capture into an organized album directory that preserves the different variants.

See docs/domain.md for the Image Capture file structure and docs/internals.md
for the album layout.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from ...common.fs import file_ext, list_files
from ..store.media_sources import ios_img_number, pick_media_priority
from ..store.protocol import (
    IOS_IMG_EXTENSIONS,
    IOS_SIDECAR_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    MediaSource,
)
from .collision import ArchiveCollision
from .selection import SelectionSources, read_selection, write_selection_csv

if TYPE_CHECKING:
    from .tasks import ImportTask


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


def _is_img(filename: str) -> bool:
    return file_ext(filename) in IOS_IMG_EXTENSIONS


def _is_mov(filename: str) -> bool:
    return file_ext(filename) in IOS_VID_EXTENSIONS


def _is_sidecar(filename: str) -> bool:
    return file_ext(filename) in IOS_SIDECAR_EXTENSIONS


def _is_media(filename: str) -> bool:
    return _is_img(filename) or _is_mov(filename)


def _media_type(filename: str) -> MediaType | None:
    match file_ext(filename):
        case ext if ext in IOS_IMG_EXTENSIONS:
            return MediaType.IMAGE
        case ext if ext in IOS_VID_EXTENSIONS:
            return MediaType.VIDEO
        case _:
            return None


def _is_img_prefixed(filename: str) -> bool:
    return filename.lower().startswith("img_")


# ---------------------------------------------------------------------------
# Import plan — maps selection files to IC files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionMatch:
    """A selection file and the IC files it resolves to."""

    selection_file: str
    img_number: str
    media_type: MediaType
    orig_files: tuple[str, ...]
    rendered_files: tuple[str, ...]
    # Live Photo: companion files of the opposite media type
    is_live_photo: bool = False
    companion_orig_files: tuple[str, ...] = ()
    companion_rendered_files: tuple[str, ...] = ()

    @property
    def routes_to_images(self) -> bool:
        """Whether the match lands in the image dirs.

        Live Photos always do: the image and its companion video are a unit.
        """
        return self.is_live_photo or self.media_type == MediaType.IMAGE


@dataclass(frozen=True)
class DedupWarning:
    """Several format variants of one number exist; only *kept* is imported."""

    img_number: str
    kept: str
    dropped: str


@dataclass(frozen=True)
class ImportPlan:
    """Result of planning an import — maps selection files to IC files."""

    matches: tuple[SelectionMatch, ...]
    unmatched: tuple[str, ...]
    dedup_warnings: tuple[DedupWarning, ...] = ()


class ValidationErrorKind(StrEnum):
    NO_MATCHING_ORIGINAL = "no-matching-original"
    MULTIPLE_ORIGINALS = "multiple-originals"
    MULTIPLE_RENDERED = "multiple-rendered"
    ORPHAN_RENDERED_SIDECAR = "orphan-rendered-sidecar"
    MULTIPLE_LIVE_PHOTO_COMPANIONS = "multiple-live-photo-companions"
    MULTIPLE_RENDERED_LIVE_PHOTO_COMPANIONS = "multiple-rendered-live-photo-companions"


class ValidationWarningKind(StrEnum):
    MISSING_ORIGINAL_SIDECAR = "missing-original-sidecar"
    MISSING_RENDERED_SIDECAR = "missing-rendered-sidecar"


@dataclass(frozen=True)
class ValidationError:
    """A validation error for a specific selection file.

    *files* are the Image Capture files involved (e.g. the colliding
    originals for ``MULTIPLE_ORIGINALS``).
    """

    selection_file: str
    kind: ValidationErrorKind
    img_number: str = ""
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationWarning:
    """A non-fatal warning for a specific selection file."""

    selection_file: str
    kind: ValidationWarningKind
    file: str


@dataclass(frozen=True)
class IosSourceImportResult:
    """Result of importing a single iOS media source.

    *unprocessed* lists selection entries whose image number was imported but
    that are still present in the staging dir or CSV after cleanup. A
    leftover entry would make the next ``album import`` collide with the
    media it already brought in, so a non-empty value is reported as a
    failure.
    """

    media_source_name: str
    plan: ImportPlan
    processed: frozenset[str]
    unprocessed: tuple[str, ...]


def _group_by_number(files: Iterable[str]) -> dict[str, list[str]]:
    """Group filenames by image number, preserving their relative order."""
    by_number = sorted(files, key=ios_img_number)
    return {num: list(group) for num, group in groupby(by_number, key=ios_img_number)}


def _build_ic_index(image_capture_files: list[str]) -> dict[str, list[str]]:
    """Index IC files by their numeric portion for fast lookup."""
    return _group_by_number(f for f in image_capture_files if _is_img_prefixed(f))


def _dedup_media_by_number(
    files: tuple[str, ...],
    is_primary: Callable[[str], bool],
) -> tuple[tuple[str, ...], tuple[DedupWarning, ...]]:
    """Deduplicate media files by number, preferring DNG > HEIC > JPG/PNG.

    Handles the iOS edge case where multiple format variants exist for the
    same photo (e.g. IMG_E7658.JPG + IMG_E7658.HEIC). DNG (ProRAW) is
    preferred as the highest-quality format, followed by HEIC.

    Returns ``(deduped_files, warnings)`` where warnings describe dropped files.
    Sidecar (AAE) files are never deduplicated -- only media files.
    """
    media_by_number = sorted(
        _group_by_number(f for f in files if is_primary(f)).items()
    )
    winners = {
        num: pick_media_priority(candidates) for num, candidates in media_by_number
    }
    warnings = tuple(
        DedupWarning(img_number=num, kept=winners[num], dropped=f)
        for num, candidates in media_by_number
        for f in candidates
        if f != winners[num]
    )
    non_media = tuple(f for f in files if not is_primary(f))
    return (*winners.values(), *non_media), warnings


def _classify_ic_files(
    ic_files: list[str], media_type: MediaType
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[DedupWarning, ...]]:
    """Classify IC files into (orig, edited, dedup_warnings) based on media type.

    Media files are deduplicated by number with HEIC priority to handle the
    undocumented iOS edge case of duplicate edited variants.

    Note: AAE sidecars for videos are unconfirmed but accepted
    to avoid false failures if Apple changes the format.
    """
    match media_type:
        case MediaType.IMAGE:
            is_primary = _is_img
        case MediaType.VIDEO:
            is_primary = _is_mov

    raw_orig = tuple(
        f
        for f in ic_files
        if (
            (is_primary(f) and not f.lower().startswith("img_e"))
            or (_is_sidecar(f) and not f.lower().startswith("img_o"))
        )
    )
    raw_rendered = tuple(
        f
        for f in ic_files
        if (
            (is_primary(f) and f.lower().startswith("img_e"))
            or (_is_sidecar(f) and f.lower().startswith("img_o"))
        )
    )

    orig, orig_warnings = _dedup_media_by_number(raw_orig, is_primary)
    rendered, rendered_warnings = _dedup_media_by_number(raw_rendered, is_primary)

    return orig, rendered, (*orig_warnings, *rendered_warnings)


def _companion_type(media_type: MediaType) -> MediaType:
    match media_type:
        case MediaType.IMAGE:
            return MediaType.VIDEO
        case MediaType.VIDEO:
            return MediaType.IMAGE


def _build_match(
    sel_file: str, media_type: MediaType, ic_files: list[str]
) -> tuple[SelectionMatch | None, tuple[DedupWarning, ...]]:
    """Resolve *sel_file* against the IC files sharing its number."""
    orig, rendered, dedup_warnings = _classify_ic_files(ic_files, media_type)
    if not any(_is_media(f) for f in orig):
        return None, dedup_warnings
    else:
        # Detect Live Photo: check if companion media type also exists
        comp_orig, comp_rendered, comp_dedup = _classify_ic_files(
            ic_files, _companion_type(media_type)
        )
        has_companion = any(_is_media(f) for f in comp_orig)
        return SelectionMatch(
            selection_file=sel_file,
            img_number=ios_img_number(sel_file),
            media_type=media_type,
            orig_files=orig,
            rendered_files=rendered,
            is_live_photo=has_companion,
            companion_orig_files=comp_orig if has_companion else (),
            companion_rendered_files=comp_rendered if has_companion else (),
        ), (*dedup_warnings, *comp_dedup)


def _match_selection_file(
    sel_file: str, ic_index: dict[str, list[str]]
) -> tuple[SelectionMatch | None, tuple[DedupWarning, ...]]:
    """Match a single selection file to its IC files, or return (None, warnings) if unmatched."""
    match _media_type(sel_file):
        case None:
            return None, ()
        case media_type:
            return _build_match(
                sel_file, media_type, ic_index.get(ios_img_number(sel_file), [])
            )


def plan_import(
    selection_files: list[str],
    image_capture_files: list[str],
) -> ImportPlan:
    """Build an import plan by matching selection files to IC files.

    For each selection file, determines its media type and number, then finds
    the corresponding original and edited files in the IC directory.
    Selection files may be JPEG even if IC originals are HEIC — matching is by number.
    """
    ic_index = _build_ic_index(image_capture_files)
    results = [
        (sel_file, *_match_selection_file(sel_file, ic_index))
        for sel_file in selection_files
    ]

    return ImportPlan(
        matches=tuple(m for _, m, _ in results if m is not None),
        unmatched=tuple(sel_file for sel_file, m, _ in results if m is None),
        dedup_warnings=tuple(w for _, _, warnings in results for w in warnings),
    )


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


def _error_if(
    condition: bool,
    match: SelectionMatch,
    kind: ValidationErrorKind,
    files: list[str],
) -> list[ValidationError]:
    return (
        [ValidationError(match.selection_file, kind, match.img_number, tuple(files))]
        if condition
        else []
    )


def _validate_companion(match: SelectionMatch) -> list[ValidationError]:
    """Validate Live Photo companion files. Returns errors."""
    comp_media = [f for f in match.companion_orig_files if _is_media(f)]
    comp_rendered_media = [f for f in match.companion_rendered_files if _is_media(f)]
    return [
        *_error_if(
            len(comp_media) > 1,
            match,
            ValidationErrorKind.MULTIPLE_LIVE_PHOTO_COMPANIONS,
            comp_media,
        ),
        *_error_if(
            len(comp_rendered_media) > 1,
            match,
            ValidationErrorKind.MULTIPLE_RENDERED_LIVE_PHOTO_COMPANIONS,
            comp_rendered_media,
        ),
    ]


def _match_errors(match: SelectionMatch) -> list[ValidationError]:
    """Structural errors for a single selection match."""
    orig_media = [f for f in match.orig_files if _is_media(f)]
    rendered_media = [f for f in match.rendered_files if _is_media(f)]
    rendered_sidecars = [f for f in match.rendered_files if _is_sidecar(f)]
    return [
        # Multiple originals suggest a number collision (e.g. airdropped files
        # sharing the same numeric ID as a camera-taken photo).
        *_error_if(
            len(orig_media) > 1,
            match,
            ValidationErrorKind.MULTIPLE_ORIGINALS,
            orig_media,
        ),
        *_error_if(
            len(rendered_media) > 1,
            match,
            ValidationErrorKind.MULTIPLE_RENDERED,
            rendered_media,
        ),
        # Rendered sidecar without rendered media is orphaned edit data.
        *_error_if(
            bool(rendered_sidecars) and not rendered_media,
            match,
            ValidationErrorKind.ORPHAN_RENDERED_SIDECAR,
            rendered_sidecars[:1],
        ),
        *(_validate_companion(match) if match.is_live_photo else []),
    ]


def _match_warnings(match: SelectionMatch) -> list[ValidationWarning]:
    """AAE sidecars are optional in Image Capture exports — warn, don't block."""
    orig_heic = [f for f in match.orig_files if file_ext(f) == ".heic"]
    orig_aae = [f for f in match.orig_files if _is_sidecar(f)]
    rendered_media = [f for f in match.rendered_files if _is_media(f)]
    rendered_sidecars = [f for f in match.rendered_files if _is_sidecar(f)]
    return [
        *(
            [
                ValidationWarning(
                    match.selection_file,
                    ValidationWarningKind.MISSING_ORIGINAL_SIDECAR,
                    orig_heic[0],
                )
            ]
            if orig_heic and not orig_aae
            else []
        ),
        *(
            [
                ValidationWarning(
                    match.selection_file,
                    ValidationWarningKind.MISSING_RENDERED_SIDECAR,
                    rendered_media[0],
                )
            ]
            if rendered_media and not rendered_sidecars
            else []
        ),
    ]


def validate_import_plan(
    plan: ImportPlan,
) -> tuple[list[ValidationError], list[ValidationWarning]]:
    """Validate an import plan. Returns (errors, warnings)."""
    errors = [
        *(
            ValidationError(f, ValidationErrorKind.NO_MATCHING_ORIGINAL)
            for f in plan.unmatched
        ),
        *(e for m in plan.matches for e in _match_errors(m)),
    ]
    warnings = [w for m in plan.matches for w in _match_warnings(m)]
    return errors, warnings


# ---------------------------------------------------------------------------
# Archive collisions
# ---------------------------------------------------------------------------


def _archive_numbers(directory: Path) -> set[str]:
    return {
        ios_img_number(f)
        for f in list_files(directory)
        if _is_media(f) or _is_sidecar(f)
    }


def find_ios_collision(
    album_dir: Path, ms: MediaSource, plan: ImportPlan
) -> ArchiveCollision | None:
    """Return the planned image numbers already present in *ms*'s archive.

    Matched by image number regardless of extension. Live Photos are checked
    against ``orig-img`` since both of their files land there.
    """
    incoming_img = {m.img_number for m in plan.matches if m.routes_to_images}
    incoming_vid = {m.img_number for m in plan.matches if not m.routes_to_images}
    collisions = sorted(
        (incoming_img & _archive_numbers(album_dir / ms.orig_img_dir))
        | (incoming_vid & _archive_numbers(album_dir / ms.orig_vid_dir))
    )
    return ArchiveCollision(ms, tuple(collisions)) if collisions else None


def plan_ios_task(task: ImportTask, image_capture_files: list[str]) -> ImportPlan:
    """Plan an iOS task from its merged selection."""
    sources = read_selection(task.selection_dir, task.selection_csv)
    return plan_import(list(sources.merged), image_capture_files)


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def _copy_files(src_dir: Path, dst_dir: Path, files: tuple[str, ...]) -> None:
    """Copy *files*, creating *dst_dir* only when there is something to copy.

    Creating directories on demand avoids empty leftovers (e.g. ``orig-img/``
    in a video-only album).
    """
    if files:
        dst_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy(src_dir / f, dst_dir)


def _copy_match(
    album_dir: Path, ms: MediaSource, image_capture_dir: Path, match: SelectionMatch
) -> None:
    orig_dir, rendered_dir = (
        (ms.orig_img_dir, ms.edit_img_dir)
        if match.routes_to_images
        else (ms.orig_vid_dir, ms.edit_vid_dir)
    )
    _copy_files(
        image_capture_dir,
        album_dir / orig_dir,
        (*match.orig_files, *match.companion_orig_files),
    )
    _copy_files(
        image_capture_dir,
        album_dir / rendered_dir,
        (*match.rendered_files, *match.companion_rendered_files),
    )


def _consume_selection(
    task: ImportTask, sources: SelectionSources, processed_numbers: frozenset[str]
) -> None:
    """Remove every selection entry whose image number was imported.

    Removal is by image number rather than by the merged filename: the merge
    keeps one entry per number, so a Live Photo exported as both
    ``IMG_0001.HEIC`` and ``IMG_0001.MOV``, or a number listed in both the dir
    and the CSV, would otherwise leave entries behind that collide with the
    imported media on the next run. The CSV is deleted once all of its
    numbers are processed, and otherwise rewritten with the remaining rows.
    """
    if task.selection_dir is not None:
        for f in sources.dir_files:
            if ios_img_number(f) in processed_numbers:
                (task.selection_dir / f).unlink(missing_ok=True)
    if task.selection_csv is not None and sources.csv_files:
        remaining = [
            f for f in sources.csv_files if ios_img_number(f) not in processed_numbers
        ]
        if remaining:
            write_selection_csv(task.selection_csv, remaining)
        else:
            task.selection_csv.unlink(missing_ok=True)


def _leftover_entries(
    task: ImportTask, processed_numbers: frozenset[str]
) -> tuple[str, ...]:
    """Selection entries still present for a number that was imported."""
    sources = read_selection(task.selection_dir, task.selection_csv)
    return tuple(
        sorted(
            {
                f
                for f in (*sources.dir_files, *sources.csv_files)
                if ios_img_number(f) in processed_numbers
            }
        )
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_ios_source(
    album_dir: Path,
    task: ImportTask,
    image_capture_dir: Path,
    image_capture_files: list[str],
    *,
    dry_run: bool = False,
) -> IosSourceImportResult:
    """Copy an iOS source's selected files from Image Capture into its archive.

    Copies matched originals and edits into the ``ios-<name>/`` archive, then
    removes processed selection entries from the staging dir and CSV.

    The archive collision check (:func:`find_ios_collision`) is the caller's
    job, before any mutation: :func:`photree.album.importer.album_import.run_import`
    runs it for every task up front. Browsable, JPEG, and other derived data
    are refreshed once by that orchestrator after all sources are imported.
    """
    ms = task.media_source
    sources = read_selection(task.selection_dir, task.selection_csv)
    plan = plan_import(list(sources.merged), image_capture_files)
    processed_numbers = frozenset(m.img_number for m in plan.matches)

    if not dry_run:
        for match in plan.matches:
            _copy_match(album_dir, ms, image_capture_dir, match)
        _consume_selection(task, sources, processed_numbers)

    return IosSourceImportResult(
        media_source_name=ms.name,
        plan=plan,
        processed=frozenset(m.selection_file for m in plan.matches),
        unprocessed=() if dry_run else _leftover_entries(task, processed_numbers),
    )
