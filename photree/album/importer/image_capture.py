"""Import photos from macOS Image Capture into an organized album directory that preserves the different variants.

See docs/internals.md for the Image Capture file structure and album layout.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...common.fs import list_files
from ...fsprotocol import PHOTREE_DIR, LinkMode
from .. import browsable
from ..jpeg import convert_single_file, refresh_jpeg_dir
from ..store.metadata import save_album_metadata
from ..store.media_sources import pick_media_priority
from ..store.protocol import (
    ALBUM_YAML,
    DEFAULT_MEDIA_SOURCE,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    SELECTION_DIR,
    SIDECAR_EXTENSIONS,
    AlbumMetadata,
    generate_album_id,
    ios_media_source,
)

# Import stages
STAGE_IMPORT_IC = "import-ic"
STAGE_REFRESH_MAIN_IMG = "refresh-main-img"
STAGE_REFRESH_MAIN_VID = "refresh-main-vid"
STAGE_REFRESH_MAIN_JPG = "refresh-main-jpg"


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _is_img(filename: str) -> bool:
    return _ext(filename) in IOS_IMG_EXTENSIONS


def _is_mov(filename: str) -> bool:
    return _ext(filename) in IOS_VID_EXTENSIONS


def _is_sidecar(filename: str) -> bool:
    return _ext(filename) in SIDECAR_EXTENSIONS


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
class ImportResult:
    """Result of running an import."""

    plan: ImportPlan
    processed: frozenset[str]
    unprocessed: tuple[str, ...]


def plan_import_from_dirs(
    selection_dir: Path,
    image_capture_dir: Path,
) -> ImportPlan:
    """Build an import plan by reading files from the given directories."""
    return plan_import(_list_files(selection_dir), _list_files(image_capture_dir))


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
            return SelectionMatch(
                selection_file=sel_file,
                img_number=_img_number(sel_file),
                media_type=mt,
                orig_files=orig,
                rendered_files=rendered,
            ), dedup_warnings


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


def _validate_match(match: SelectionMatch) -> list[ValidationError]:
    """Validate a single selection match. Returns errors found."""
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

    # Rendered pair completeness
    rendered_pair_errors = [
        *(
            [
                ValidationError(
                    match.selection_file,
                    f"rendered file exists ({rendered_media[0]}) but no rendered sidecar (IMG_O*.AAE)",
                )
            ]
            if rendered_media and not rendered_sidecars
            else []
        ),
        *(
            [
                ValidationError(
                    match.selection_file,
                    f"rendered sidecar exists ({rendered_sidecars[0]}) but no rendered media file",
                )
            ]
            if rendered_sidecars and not rendered_media
            else []
        ),
    ]

    # HEIC should have AAE
    orig_heic = [f for f in orig_media if _ext(f) == ".heic"]
    orig_aae = [f for f in match.orig_files if _is_sidecar(f)]
    heic_aae_errors = (
        [
            ValidationError(
                match.selection_file,
                f"original HEIC ({orig_heic[0]}) has no AAE sidecar (unusual)",
            )
        ]
        if orig_heic and not orig_aae
        else []
    )

    return [
        *type_errors,
        *orig_count_errors,
        *rendered_count_errors,
        *rendered_pair_errors,
        *heic_aae_errors,
    ]


def validate_import_plan(plan: ImportPlan) -> list[ValidationError]:
    """Validate an import plan. Returns a list of errors (empty = all good)."""
    return [
        # Unmatched selection files
        *[
            ValidationError(f, "no matching original found in Image Capture directory")
            for f in plan.unmatched
        ],
        # Per-match validation
        *(error for match in plan.matches for error in _validate_match(match)),
    ]


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def _list_files(directory: Path) -> list[str]:
    """Return regular file names inside *directory*, ignoring dotfiles (e.g. .DS_Store)."""
    return list_files(directory)


def _copy_file(src_dir: Path, dst_dir: Path, filename: str, *, dry_run: bool) -> None:
    if not dry_run:
        shutil.copy(src_dir / filename, dst_dir)


def _remove_empty_folders(root: Path) -> None:
    for dirpath, _dirnames, _filenames in list(os.walk(root))[::-1]:
        p = Path(dirpath)
        if p == root or p.name.startswith("."):
            continue
        if not os.listdir(dirpath):
            os.rmdir(dirpath)


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


def _notify(callback: Callable[[str], None] | None, value: str) -> None:
    if callback:
        callback(value)


def run_import(
    *,
    album_dir: Path,
    image_capture_dir: Path,
    media_source_name: str = DEFAULT_MEDIA_SOURCE,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
) -> ImportResult:
    """Organize Image Capture files into an album directory.

    Returns an :class:`ImportResult` with the plan and processed/unprocessed tracking.

    The import runs in four stages:
    1. ``import-ic`` — copy files from Image Capture to orig/edited dirs
    2. ``refresh-main-img`` — build main-img from orig-img + edit-img
    3. ``refresh-main-vid`` — build main-vid from orig-vid + edit-vid
    4. ``refresh-main-jpg`` — build main-jpg from main-img

    Callbacks:
    - ``on_stage_start(stage)`` — called before each stage
    - ``on_stage_end(stage)`` — called after each stage

    Parameters:
    - ``convert_file(src, dst_dir, dry_run=)`` — per-file HEIC→JPEG converter (default: sips via album.jpeg)
    """
    album_selection = album_dir / SELECTION_DIR

    # Read input files
    selection_files = _list_files(album_selection)
    image_capture_files = _list_files(image_capture_dir)

    if not selection_files:
        raise FileNotFoundError(
            f"Could not find any selection files in {album_selection}"
        )
    if not image_capture_files:
        raise FileNotFoundError(
            f"Could not find any image capture files in {image_capture_dir}"
        )

    # Plan
    plan = plan_import(selection_files, image_capture_files)

    # Output directories — derived from media source (always iOS for Image Capture)
    ms = ios_media_source(media_source_name)
    album_orig_img = album_dir / ms.orig_img_dir
    album_orig_vid = album_dir / ms.orig_vid_dir
    album_edit_img = album_dir / ms.edit_img_dir
    album_edit_vid = album_dir / ms.edit_vid_dir
    album_main_img = album_dir / ms.img_dir
    album_main_jpg = album_dir / ms.jpg_dir

    # Create album marker and metadata so gallery commands can discover this album
    if not dry_run:
        (album_dir / PHOTREE_DIR).mkdir(exist_ok=True)
        if not (album_dir / PHOTREE_DIR / ALBUM_YAML).is_file():
            save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))

    # ── Pre-copy collision check ──
    # Fail fast before copying anything if the target media source already
    # contains files with the same image number (even with a different extension).
    incoming_img_numbers = {
        match.img_number
        for match in plan.matches
        if match.media_type == MediaType.IMAGE
    }
    incoming_vid_numbers = {
        match.img_number
        for match in plan.matches
        if match.media_type == MediaType.VIDEO
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
            + f"Use --media-source to import into a different media source (current: {ms.name})."
        )

    # ── Stage 1: import-ic ──
    # Copy files from Image Capture to orig/edited dirs.
    # Directories are created on demand to avoid empty leftover dirs
    # (e.g. orig-img/ in a video-only album).
    _notify(on_stage_start, STAGE_IMPORT_IC)

    processed: set[str] = set()

    for match in plan.matches:
        orig_dir = _dir_for_type(
            match.media_type, img_dir=album_orig_img, vid_dir=album_orig_vid
        )
        rendered_dir = _dir_for_type(
            match.media_type,
            img_dir=album_edit_img,
            vid_dir=album_edit_vid,
        )

        if not dry_run and match.orig_files:
            orig_dir.mkdir(parents=True, exist_ok=True)
        for f in match.orig_files:
            _copy_file(image_capture_dir, orig_dir, f, dry_run=dry_run)

        if not dry_run and match.rendered_files:
            rendered_dir.mkdir(parents=True, exist_ok=True)
        for f in match.rendered_files:
            _copy_file(image_capture_dir, rendered_dir, f, dry_run=dry_run)

        processed.add(match.selection_file)

    _notify(on_stage_end, STAGE_IMPORT_IC)

    # ── Stage 2: refresh-main-img ──
    _notify(on_stage_start, STAGE_REFRESH_MAIN_IMG)
    browsable.refresh_browsable_dir(
        album_orig_img,
        album_edit_img,
        album_main_img,
        media_extensions=IOS_IMG_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    _notify(on_stage_end, STAGE_REFRESH_MAIN_IMG)

    # ── Stage 3: refresh-main-vid ──
    _notify(on_stage_start, STAGE_REFRESH_MAIN_VID)
    browsable.refresh_browsable_dir(
        album_orig_vid,
        album_edit_vid,
        album_dir / ms.vid_dir,
        media_extensions=IOS_VID_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    _notify(on_stage_end, STAGE_REFRESH_MAIN_VID)

    # ── Stage 4: refresh-main-jpg ──
    _notify(on_stage_start, STAGE_REFRESH_MAIN_JPG)
    refresh_jpeg_dir(
        album_main_img,
        album_main_jpg,
        dry_run=dry_run,
        convert_file=convert_file,
    )
    _notify(on_stage_end, STAGE_REFRESH_MAIN_JPG)

    # Sanity check: all matched selection files should have been processed
    all_matched = {m.selection_file for m in plan.matches}
    unprocessed = sorted(all_matched - processed)

    # Cleanup: only delete processed selection files, keep unmatched ones
    if not dry_run:
        for sel_file in processed:
            (album_selection / sel_file).unlink(missing_ok=True)
        _remove_empty_folders(album_dir)

    return ImportResult(
        plan=plan,
        processed=frozenset(processed),
        unprocessed=tuple(unprocessed),
    )
