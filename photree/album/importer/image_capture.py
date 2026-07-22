"""Import photos from macOS Image Capture into an organized album directory that preserves the different variants.

See docs/internals.md for the Image Capture file structure and album layout.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from ...common.fs import file_ext, list_files
from ..store.media_sources import pick_media_priority
from ..store.protocol import (
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    IOS_SIDECAR_EXTENSIONS,
)

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
    if _is_img(filename):
        return MediaType.IMAGE
    elif _is_mov(filename):
        return MediaType.VIDEO
    else:
        return None


def _img_number(filename: str) -> str:
    """Extract the numeric portion of a filename (e.g. '0410' from 'IMG_0410.HEIC')."""
    return "".join(c for c in filename if c.isdigit())


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


@dataclass(frozen=True)
class ImportPlan:
    """Result of planning an import — maps selection files to IC files."""

    matches: tuple[SelectionMatch, ...]
    unmatched: tuple[str, ...]
    dedup_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationError:
    """A validation error for a specific selection file."""

    selection_file: str
    message: str


@dataclass(frozen=True)
class ValidationWarning:
    """A non-fatal warning for a specific selection file."""

    selection_file: str
    message: str


@dataclass(frozen=True)
class IosSourceImportResult:
    """Result of importing a single iOS media source."""

    media_source_name: str
    plan: ImportPlan
    processed: frozenset[str]
    unprocessed: tuple[str, ...]


def _build_ic_index(image_capture_files: list[str]) -> dict[str, list[str]]:
    """Index IC files by their numeric portion for fast lookup."""
    index: dict[str, list[str]] = {}
    for f in image_capture_files:
        if _is_img_prefixed(f):
            index.setdefault(_img_number(f), []).append(f)
    return index


def _dedup_media_by_number(
    files: tuple[str, ...],
    is_primary: Callable[[str], bool],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deduplicate media files by number, preferring DNG > HEIC > JPG/PNG.

    Handles the iOS edge case where multiple format variants exist for the
    same photo (e.g. IMG_E7658.JPG + IMG_E7658.HEIC). DNG (ProRAW) is
    preferred as the highest-quality format, followed by HEIC.

    Returns ``(deduped_files, warnings)`` where warnings describe dropped files.
    Sidecar (AAE) files are never deduplicated -- only media files.
    """
    # Group media files by number
    media_by_number: dict[str, list[str]] = {}
    non_media = [f for f in files if not is_primary(f)]

    for f in files:
        if is_primary(f):
            media_by_number.setdefault(_img_number(f), []).append(f)

    deduped: list[str] = []
    warnings: list[str] = []

    for num, candidates in sorted(media_by_number.items()):
        if len(candidates) == 1:
            deduped.append(candidates[0])
        else:
            winner = pick_media_priority(candidates)
            dropped = [f for f in candidates if f != winner]
            deduped.append(winner)
            for d in dropped:
                warnings.append(
                    f"{d} dropped in favor of {winner} (duplicate number {num})"
                )

    return tuple([*deduped, *non_media]), tuple(warnings)


def _classify_ic_files(
    ic_files: list[str], media_type: MediaType
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
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


def _match_selection_file(
    sel_file: str, ic_index: dict[str, list[str]]
) -> tuple[SelectionMatch | None, tuple[str, ...]]:
    """Match a single selection file to its IC files, or return (None, warnings) if unmatched."""
    mt = _media_type(sel_file)
    if mt is None:
        return None, ()
    else:
        ic_files = ic_index.get(_img_number(sel_file), [])
        orig, rendered, dedup_warnings = _classify_ic_files(ic_files, mt)
        has_orig_media = any(_is_media(f) for f in orig)
        if not has_orig_media:
            return None, dedup_warnings
        else:
            # Detect Live Photo: check if companion media type also exists
            match mt:
                case MediaType.IMAGE:
                    companion_mt = MediaType.VIDEO
                case MediaType.VIDEO:
                    companion_mt = MediaType.IMAGE
            comp_orig, comp_rendered, comp_dedup = _classify_ic_files(
                ic_files, companion_mt
            )
            has_companion = any(_is_media(f) for f in comp_orig)
            return SelectionMatch(
                selection_file=sel_file,
                img_number=_img_number(sel_file),
                media_type=mt,
                orig_files=orig,
                rendered_files=rendered,
                is_live_photo=has_companion,
                companion_orig_files=comp_orig if has_companion else (),
                companion_rendered_files=comp_rendered if has_companion else (),
            ), (*dedup_warnings, *comp_dedup)


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


def _validate_companion(match: SelectionMatch) -> list[ValidationError]:
    """Validate Live Photo companion files. Returns errors."""
    comp_media = [f for f in match.companion_orig_files if _is_media(f)]
    comp_rendered_media = [f for f in match.companion_rendered_files if _is_media(f)]
    return [
        *(
            [
                ValidationError(
                    match.selection_file,
                    f"expected 1 Live Photo companion for number "
                    f"{match.img_number} but found {len(comp_media)}: "
                    f"{', '.join(comp_media)}.",
                )
            ]
            if len(comp_media) > 1
            else []
        ),
        *(
            [
                ValidationError(
                    match.selection_file,
                    f"expected at most 1 rendered Live Photo companion for "
                    f"number {match.img_number} but found "
                    f"{len(comp_rendered_media)}: "
                    f"{', '.join(comp_rendered_media)}.",
                )
            ]
            if len(comp_rendered_media) > 1
            else []
        ),
    ]


def _validate_match(
    match: SelectionMatch,
) -> tuple[list[ValidationError], list[ValidationWarning]]:
    """Validate a single selection match. Returns (errors, warnings)."""
    orig_media = [f for f in match.orig_files if _is_media(f)]
    rendered_media = [f for f in match.rendered_files if _is_media(f)]
    rendered_sidecars = [f for f in match.rendered_files if _is_sidecar(f)]

    # Type consistency — orig media should match expected type
    type_errors = {
        MediaType.IMAGE: [
            ValidationError(
                match.selection_file,
                f"image selection file matched non-image original: {f}",
            )
            for f in orig_media
            if not _is_img(f)
        ],
        MediaType.VIDEO: [
            ValidationError(
                match.selection_file,
                f"video selection file matched non-video original: {f}",
            )
            for f in orig_media
            if not _is_mov(f)
        ],
    }.get(match.media_type, [])

    # Exactly one original media file expected per selection file.
    # Multiple originals suggest a number collision (e.g. airdropped files
    # sharing the same numeric ID as a camera-taken photo).
    orig_count_errors = (
        [
            ValidationError(
                match.selection_file,
                f"expected 1 original media file for number {match.img_number} "
                f"but found {len(orig_media)}: {', '.join(orig_media)}. "
                f"This may indicate a number collision with airdropped files.",
            )
        ]
        if len(orig_media) > 1
        else []
    )

    # At most one rendered media file expected
    rendered_count_errors = (
        [
            ValidationError(
                match.selection_file,
                f"expected at most 1 rendered media file for number {match.img_number} "
                f"but found {len(rendered_media)}: {', '.join(rendered_media)}.",
            )
        ]
        if len(rendered_media) > 1
        else []
    )

    # Rendered sidecar without rendered media is a real error — orphaned edit data
    rendered_pair_errors = (
        [
            ValidationError(
                match.selection_file,
                f"rendered sidecar exists ({rendered_sidecars[0]}) but no rendered media file",
            )
        ]
        if rendered_sidecars and not rendered_media
        else []
    )

    # Live Photo companion validation
    companion_errors = _validate_companion(match) if match.is_live_photo else []

    errors = [
        *type_errors,
        *orig_count_errors,
        *rendered_count_errors,
        *rendered_pair_errors,
        *companion_errors,
    ]

    # AAE sidecars are optional in Image Capture exports — warn, don't block.
    orig_heic = [f for f in orig_media if file_ext(f) == ".heic"]
    orig_aae = [f for f in match.orig_files if _is_sidecar(f)]
    warnings = [
        *(
            [
                ValidationWarning(
                    match.selection_file,
                    f"original HEIC ({orig_heic[0]}) has no AAE sidecar",
                )
            ]
            if orig_heic and not orig_aae
            else []
        ),
        *(
            [
                ValidationWarning(
                    match.selection_file,
                    f"rendered file ({rendered_media[0]}) has no rendered sidecar (IMG_O*.AAE)",
                )
            ]
            if rendered_media and not rendered_sidecars
            else []
        ),
    ]

    return errors, warnings


def validate_import_plan(
    plan: ImportPlan,
) -> tuple[list[ValidationError], list[ValidationWarning]]:
    """Validate an import plan. Returns (errors, warnings)."""
    match_results = [_validate_match(m) for m in plan.matches]
    errors = [
        *[
            ValidationError(f, "no matching original found in Image Capture directory")
            for f in plan.unmatched
        ],
        *(e for errs, _ in match_results for e in errs),
    ]
    warnings = [w for _, warns in match_results for w in warns]
    return errors, warnings


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def _copy_file(src_dir: Path, dst_dir: Path, filename: str, *, dry_run: bool) -> None:
    if not dry_run:
        shutil.copy(src_dir / filename, dst_dir)


def _dir_for_type(
    media_type: MediaType,
    *,
    img_dir: Path,
    vid_dir: Path,
) -> Path:
    match media_type:
        case MediaType.IMAGE:
            return img_dir
        case MediaType.VIDEO:
            return vid_dir


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

    Runs the pre-copy collision check, copies matched originals and edits into
    the ``ios-<name>/`` archive, then removes processed selection entries from
    the staging dir (and the CSV when fully consumed).

    Browsable, JPEG, and other derived data are refreshed once by the
    orchestrator (:func:`photree.album.importer.album_import.run_import`) after
    all sources have been imported.
    """
    from .selection import read_selection

    ms = task.media_source
    sources = read_selection(task.selection_dir, task.selection_csv)
    selection_files = list(sources.merged)

    plan = plan_import(selection_files, image_capture_files)

    album_orig_img = album_dir / ms.orig_img_dir
    album_orig_vid = album_dir / ms.orig_vid_dir
    album_edit_img = album_dir / ms.edit_img_dir
    album_edit_vid = album_dir / ms.edit_vid_dir

    # ── Pre-copy collision check ──
    # Fail fast before copying anything if the target media source already
    # contains files with the same image number (even with a different extension).
    # Live Photos always route to orig-img (both image and companion video).
    incoming_img_numbers = {
        match.img_number
        for match in plan.matches
        if match.media_type == MediaType.IMAGE or match.is_live_photo
    }
    incoming_vid_numbers = {
        match.img_number
        for match in plan.matches
        if match.media_type == MediaType.VIDEO and not match.is_live_photo
    }
    existing_img = {
        _img_number(f)
        for f in list_files(album_orig_img)
        if _is_media(f) or _is_sidecar(f)
    }
    existing_vid = {
        _img_number(f)
        for f in list_files(album_orig_vid)
        if _is_media(f) or _is_sidecar(f)
    }
    img_collisions = incoming_img_numbers & existing_img
    vid_collisions = incoming_vid_numbers & existing_vid
    if img_collisions or vid_collisions:
        collision_numbers = sorted(img_collisions | vid_collisions)
        raise ValueError(
            f"Import would conflict with {len(collision_numbers)} existing"
            f" image number(s) in media source '{ms.name}':\n"
            + "".join(f"  IMG #{n}\n" for n in collision_numbers[:10])
            + (
                f"  ... and {len(collision_numbers) - 10} more\n"
                if len(collision_numbers) > 10
                else ""
            )
            + f"Import into a different media source by renaming the staging "
            f"directory (current: to-import-ios-{ms.name})."
        )

    # ── Copy files from Image Capture to orig/edited dirs ──
    # Directories are created on demand to avoid empty leftover dirs
    # (e.g. orig-img/ in a video-only album).
    processed: set[str] = set()

    for match in plan.matches:
        # Live Photos always route to image dirs (both formats are a unit)
        if match.is_live_photo:
            orig_dir = album_orig_img
            rendered_dir = album_edit_img
        else:
            orig_dir = _dir_for_type(
                match.media_type,
                img_dir=album_orig_img,
                vid_dir=album_orig_vid,
            )
            rendered_dir = _dir_for_type(
                match.media_type,
                img_dir=album_edit_img,
                vid_dir=album_edit_vid,
            )

        all_orig = (*match.orig_files, *match.companion_orig_files)
        all_rendered = (*match.rendered_files, *match.companion_rendered_files)

        if not dry_run and all_orig:
            orig_dir.mkdir(parents=True, exist_ok=True)
        for f in all_orig:
            _copy_file(image_capture_dir, orig_dir, f, dry_run=dry_run)

        if not dry_run and all_rendered:
            rendered_dir.mkdir(parents=True, exist_ok=True)
        for f in all_rendered:
            _copy_file(image_capture_dir, rendered_dir, f, dry_run=dry_run)

        processed.add(match.selection_file)

    # Cleanup: only delete processed selection files, keep unmatched ones
    if not dry_run:
        if task.selection_dir is not None:
            for sel_file in processed:
                (task.selection_dir / sel_file).unlink(missing_ok=True)
        # Delete the CSV if all its entries were processed
        if sources.csv_files and task.selection_csv is not None:
            csv_unprocessed = set(sources.csv_files) - processed
            if not csv_unprocessed:
                task.selection_csv.unlink(missing_ok=True)

    # Sanity check: all matched selection files should have been processed
    all_matched = {m.selection_file for m in plan.matches}
    unprocessed = sorted(all_matched - processed)

    return IosSourceImportResult(
        media_source_name=ms.name,
        plan=plan,
        processed=frozenset(processed),
        unprocessed=tuple(unprocessed),
    )
