"""Album-level face detection refresh — scan, diff, detect, merge, save."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
from insightface.app import FaceAnalysis

from ...common.fs import list_files
from ...common.parallelism import run_parallel
from ..store.media_sources import dedup_media_dict
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import IMG_EXTENSIONS, IOS_IMG_EXTENSIONS, MediaSource
from .detect import (
    DetectedFace,
    ThumbnailResult,
    create_face_analyzer,
    detect_faces,
    generate_thumbnail,
    thumb_filename,
)
from .protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessedKey,
    FaceProcessingState,
)
from .store import (
    FaceData,
    filter_face_data,
    load_face_data,
    load_face_state,
    merge_face_data,
    save_face_data,
    save_face_state,
    thumbs_dir,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceSourceRefreshResult:
    """Result of refreshing face data for a single media source."""

    processed: int
    skipped: int
    faces_detected: int
    failed: int

    @property
    def changed(self) -> bool:
        return self.processed > 0 or self.failed > 0


@dataclass(frozen=True)
class FaceRefreshResult:
    """Result of refreshing face data for an album."""

    by_media_source: tuple[tuple[str, FaceSourceRefreshResult], ...]

    @property
    def total_processed(self) -> int:
        return sum(r.processed for _, r in self.by_media_source)

    @property
    def total_faces(self) -> int:
        return sum(r.faces_detected for _, r in self.by_media_source)

    @property
    def changed(self) -> bool:
        return any(r.changed for _, r in self.by_media_source)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refresh_face_data(
    album_dir: Path,
    *,
    face_analyzer: FaceAnalysis | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str = DEFAULT_MODEL_VERSION,
    redetect: bool = False,
    refresh_thumbs: bool = False,
    dry_run: bool = False,
    on_source_start: Callable[[str], None] | None = None,
    on_source_end: Callable[[str, bool], None] | None = None,
) -> FaceRefreshResult:
    """Scan album media sources and run face detection on new/changed images.

    *face_analyzer* can be shared across albums in batch operations to
    avoid reloading the model (~500 MB) for each album.
    """
    sources = discover_media_sources(album_dir)
    if not sources:
        return FaceRefreshResult(by_media_source=())

    analyzer = face_analyzer or create_face_analyzer(model_name)

    results = [
        (
            ms.name,
            _refresh_source(
                album_dir,
                ms,
                analyzer=analyzer,
                model_name=model_name,
                model_version=model_version,
                redetect=redetect,
                refresh_thumbs=refresh_thumbs,
                dry_run=dry_run,
                on_source_start=on_source_start,
                on_source_end=on_source_end,
            ),
        )
        for ms in sources
    ]

    return FaceRefreshResult(by_media_source=tuple(results))


# ---------------------------------------------------------------------------
# Per-source refresh orchestration
# ---------------------------------------------------------------------------


def _refresh_source(
    album_dir: Path,
    ms: MediaSource,
    *,
    analyzer: FaceAnalysis,
    model_name: str,
    model_version: str,
    redetect: bool,
    refresh_thumbs: bool,
    dry_run: bool,
    on_source_start: Callable[[str], None] | None,
    on_source_end: Callable[[str, bool], None] | None,
) -> FaceSourceRefreshResult:
    """Refresh face data for a single media source."""
    if on_source_start:
        on_source_start(ms.name)

    existing_state = load_face_state(album_dir, ms.name) or FaceProcessingState()
    existing_data = load_face_data(album_dir, ms.name) or FaceData.empty()

    current_files = _scan_current_images(album_dir, ms)
    current_keys = set(current_files.keys())

    model_changed = _model_version_changed(existing_state, model_name, model_version)

    keys_to_process = _keys_needing_processing(
        current_files,
        album_dir / ms.orig_img_dir,
        existing_state,
        model_changed=model_changed,
        redetect=redetect,
    )
    stale_keys = set(existing_state.processed_keys.keys()) - current_keys

    # Early returns for no-op and dry-run
    if not keys_to_process and not stale_keys:
        if on_source_end:
            on_source_end(ms.name, True)
        return _no_change_result(current_keys)

    if dry_run:
        if on_source_end:
            on_source_end(ms.name, True)
        return _dry_run_result(keys_to_process, current_keys)

    # Detect faces
    new_faces, new_state_keys, failed = _run_detection(
        album_dir,
        ms,
        current_files,
        keys_to_process,
        existing_state=existing_state,
        refresh_thumbs=refresh_thumbs or model_changed,
        analyzer=analyzer,
    )

    # Cleanup + persist
    _delete_stale_thumbnails(thumbs_dir(album_dir, ms.name), stale_keys)
    _save_updated_state(
        album_dir,
        ms,
        existing_data,
        existing_state,
        current_keys=current_keys,
        keys_to_process=keys_to_process,
        stale_keys=stale_keys,
        new_faces=new_faces,
        new_state_keys=new_state_keys,
        model_name=model_name,
        model_version=model_version,
    )

    if on_source_end:
        on_source_end(ms.name, failed == 0)

    return FaceSourceRefreshResult(
        processed=len(keys_to_process),
        skipped=len(current_keys) - len(keys_to_process),
        faces_detected=len(new_faces),
        failed=failed,
    )


# ---------------------------------------------------------------------------
# Scanning and diffing
# ---------------------------------------------------------------------------


def _scan_current_images(album_dir: Path, ms: MediaSource) -> dict[str, str]:
    """Scan ``orig-img/`` and return deduplicated ``{key: filename}`` mapping."""
    img_ext = IOS_IMG_EXTENSIONS if ms.is_ios else IMG_EXTENSIONS
    return dedup_media_dict(list_files(album_dir / ms.orig_img_dir), img_ext, ms.key_fn)


def _model_version_changed(
    state: FaceProcessingState, model_name: str, model_version: str
) -> bool:
    return state.model_name != model_name or state.model_version != model_version


def _keys_needing_processing(
    current_files: dict[str, str],
    orig_dir: Path,
    state: FaceProcessingState,
    *,
    model_changed: bool,
    redetect: bool,
) -> list[str]:
    """Return keys that need (re-)processing."""
    if redetect or model_changed:
        return sorted(current_files.keys())

    return sorted(
        key
        for key, filename in current_files.items()
        if _needs_processing(key, filename, orig_dir, state)
    )


def _needs_processing(
    key: str,
    filename: str,
    orig_dir: Path,
    state: FaceProcessingState,
) -> bool:
    """Return True when an image needs face detection."""
    entry = state.processed_keys.get(key)
    if entry is None:
        return True
    file_path = orig_dir / filename
    return file_path.is_file() and entry.mtime != file_path.stat().st_mtime


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _run_detection(
    album_dir: Path,
    ms: MediaSource,
    current_files: dict[str, str],
    keys_to_process: list[str],
    *,
    existing_state: FaceProcessingState,
    refresh_thumbs: bool,
    analyzer: FaceAnalysis,
) -> tuple[list[DetectedFace], dict[str, FaceProcessedKey], int]:
    """Generate thumbnails and run face detection.

    Returns ``(new_faces, new_state_keys, failed_count)``.
    """
    thumb_dir = thumbs_dir(album_dir, ms.name)
    thumb_results = _generate_thumbnails(
        keys_to_process,
        current_files,
        album_dir / ms.orig_img_dir,
        thumb_dir,
        existing_state=existing_state,
        regenerate=refresh_thumbs,
    )

    detection_results = [
        _detect_single(tr, album_dir / ms.orig_img_dir, analyzer)
        for tr in thumb_results
    ]

    new_faces = [
        face for faces, _ in detection_results if faces is not None for face in faces
    ]
    new_state_keys = {
        tr.key: state_key
        for tr, (_, state_key) in zip(thumb_results, detection_results)
        if state_key is not None
    }
    failed = sum(1 for faces, _ in detection_results if faces is None)

    return (new_faces, new_state_keys, failed)


def _detect_single(
    tr: ThumbnailResult,
    orig_dir: Path,
    analyzer: FaceAnalysis,
) -> tuple[list[DetectedFace] | None, FaceProcessedKey | None]:
    """Run face detection on one thumbnail. Returns ``(None, None)`` on failure."""
    try:
        detected = detect_faces(tr.key, tr.thumb_path, analyzer)
        state_key = FaceProcessedKey(
            mtime=(orig_dir / tr.file_name).stat().st_mtime,
            file_name=tr.file_name,
            face_count=len(detected),
            orig_width=tr.orig_width,
            orig_height=tr.orig_height,
            thumb_width=tr.thumb_width,
            thumb_height=tr.thumb_height,
        )
        return (detected, state_key)
    except Exception:
        return (None, None)


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------


def _generate_thumbnails(
    keys: list[str],
    current_files: dict[str, str],
    orig_dir: Path,
    thumb_dir: Path,
    *,
    existing_state: FaceProcessingState,
    regenerate: bool,
) -> list[ThumbnailResult]:
    """Generate thumbnails for keys that need them, in parallel."""
    thumb_dir.mkdir(parents=True, exist_ok=True)

    needs_thumb = [
        key
        for key in keys
        if regenerate
        or not (thumb_dir / thumb_filename(key)).is_file()
        or _needs_processing(key, current_files[key], orig_dir, existing_state)
    ]
    reuse_keys = [key for key in keys if key not in needs_thumb]

    tasks: list[tuple[str, Callable[[], ThumbnailResult]]] = [
        (
            key,
            partial(
                generate_thumbnail,
                key,
                current_files[key],
                orig_dir / current_files[key],
                thumb_dir / thumb_filename(key),
            ),
        )
        for key in needs_thumb
    ]

    generated: dict[str, ThumbnailResult] = (
        {pr.key: pr.value for pr in run_parallel(tasks) if pr.success and pr.value}
        if tasks
        else {}
    )

    reused = [
        _reuse_thumbnail(key, current_files[key], thumb_dir / thumb_filename(key))
        for key in reuse_keys
    ]

    return [
        *(generated[key] for key in needs_thumb if key in generated),
        *reused,
    ]


def _reuse_thumbnail(key: str, file_name: str, thumb_path: Path) -> ThumbnailResult:
    """Build a ThumbnailResult for an existing thumbnail."""
    from ...common.sips import get_dimensions

    thumb_w, thumb_h = get_dimensions(thumb_path)
    return ThumbnailResult(
        key=key,
        file_name=file_name,
        thumb_path=thumb_path,
        orig_width=0,
        orig_height=0,
        thumb_width=thumb_w,
        thumb_height=thumb_h,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _delete_stale_thumbnails(thumb_dir: Path, stale_keys: set[str]) -> None:
    """Remove thumbnails for keys no longer on disk."""
    for key in stale_keys:
        stale_thumb = thumb_dir / thumb_filename(key)
        if stale_thumb.is_file():
            stale_thumb.unlink()


def _save_updated_state(
    album_dir: Path,
    ms: MediaSource,
    existing_data: FaceData,
    existing_state: FaceProcessingState,
    *,
    current_keys: set[str],
    keys_to_process: list[str],
    stale_keys: set[str],
    new_faces: list[DetectedFace],
    new_state_keys: dict[str, FaceProcessedKey],
    model_name: str,
    model_version: str,
) -> None:
    """Merge detection results with existing data and save to disk."""
    keep_keys = current_keys - set(keys_to_process) - stale_keys

    retained_data = filter_face_data(existing_data, keep_keys=keep_keys)
    new_data = _faces_to_face_data(new_faces) if new_faces else FaceData.empty()
    merged_data = merge_face_data(retained_data, new_data)

    retained_state_keys = {
        k: v for k, v in existing_state.processed_keys.items() if k in keep_keys
    }
    updated_state = FaceProcessingState(
        model_name=model_name,
        model_version=model_version,
        processed_keys={**retained_state_keys, **new_state_keys},
    )

    save_face_data(album_dir, ms.name, merged_data)
    save_face_state(album_dir, ms.name, updated_state)


# ---------------------------------------------------------------------------
# Result constructors
# ---------------------------------------------------------------------------


def _no_change_result(current_keys: set[str]) -> FaceSourceRefreshResult:
    return FaceSourceRefreshResult(
        processed=0, skipped=len(current_keys), faces_detected=0, failed=0
    )


def _dry_run_result(
    keys_to_process: list[str], current_keys: set[str]
) -> FaceSourceRefreshResult:
    return FaceSourceRefreshResult(
        processed=len(keys_to_process),
        skipped=len(current_keys) - len(keys_to_process),
        faces_detected=0,
        failed=0,
    )


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _faces_to_face_data(faces: list[DetectedFace]) -> FaceData:
    """Convert a list of :class:`DetectedFace` to :class:`FaceData` arrays."""
    return FaceData(
        keys=np.array([f.key for f in faces], dtype=object),
        face_indices=np.array([f.face_index for f in faces], dtype=np.int32),
        det_scores=np.array([f.det_score for f in faces], dtype=np.float32),
        bboxes=np.stack([f.bbox for f in faces]).astype(np.float32),
        landmarks=np.stack([f.landmarks for f in faces]).astype(np.float32),
        embeddings=np.stack([f.embedding for f in faces]).astype(np.float32),
    )
