"""Face state validation — verify face data consistency with album contents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..faces.protocol import DEFAULT_MODEL_NAME, DEFAULT_MODEL_VERSION
from ..faces.store import (
    data_path,
    load_face_data,
    load_face_state,
    state_path,
    thumbs_dir,
)
from ..store.media_sources import dedup_media_dict
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import IMG_EXTENSIONS, IOS_IMG_EXTENSIONS, MediaSource
from ...common.fs import list_files


@dataclass(frozen=True)
class FaceStateCheck:
    """Result of face state validation for an album."""

    unprocessed: tuple[str, ...]
    stale_entries: tuple[str, ...]
    missing_thumbs: tuple[str, ...]
    stale_thumbs: tuple[str, ...]
    model_mismatch: bool
    npz_yaml_sync_errors: tuple[str, ...]

    @property
    def success(self) -> bool:
        return (
            len(self.unprocessed) == 0
            and len(self.stale_entries) == 0
            and len(self.missing_thumbs) == 0
            and len(self.stale_thumbs) == 0
            and not self.model_mismatch
            and len(self.npz_yaml_sync_errors) == 0
        )

    @property
    def issue_count(self) -> int:
        return (
            len(self.unprocessed)
            + len(self.stale_entries)
            + len(self.missing_thumbs)
            + len(self.stale_thumbs)
            + (1 if self.model_mismatch else 0)
            + len(self.npz_yaml_sync_errors)
        )


def check_face_state(
    album_dir: Path,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> FaceStateCheck | None:
    """Validate face detection state for an album.

    Returns ``None`` if no face data exists (not an error — just means
    face detection hasn't been run yet).
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        return None

    has_any_face_data = any(
        state_path(album_dir, ms.name).is_file()
        or data_path(album_dir, ms.name).is_file()
        for ms in media_sources
    )
    if not has_any_face_data:
        return None

    per_source = [
        _check_source(album_dir, ms, model_name=model_name, model_version=model_version)
        for ms in media_sources
    ]

    return FaceStateCheck(
        unprocessed=tuple(s for r in per_source for s in r.unprocessed),
        stale_entries=tuple(s for r in per_source for s in r.stale_entries),
        missing_thumbs=tuple(s for r in per_source for s in r.missing_thumbs),
        stale_thumbs=tuple(s for r in per_source for s in r.stale_thumbs),
        model_mismatch=any(r.model_mismatch for r in per_source),
        npz_yaml_sync_errors=tuple(
            s for r in per_source for s in r.npz_yaml_sync_errors
        ),
    )


@dataclass(frozen=True)
class _SourceCheck:
    """Per-media-source face state check result."""

    unprocessed: tuple[str, ...]
    stale_entries: tuple[str, ...]
    missing_thumbs: tuple[str, ...]
    stale_thumbs: tuple[str, ...]
    model_mismatch: bool
    npz_yaml_sync_errors: tuple[str, ...]


_EMPTY_SOURCE_CHECK = _SourceCheck(
    unprocessed=(),
    stale_entries=(),
    missing_thumbs=(),
    stale_thumbs=(),
    model_mismatch=False,
    npz_yaml_sync_errors=(),
)


def _check_source(
    album_dir: Path,
    ms: MediaSource,
    *,
    model_name: str,
    model_version: str,
) -> _SourceCheck:
    """Validate face state for a single media source."""
    state = load_face_state(album_dir, ms.name)
    if state is None:
        return _EMPTY_SOURCE_CHECK

    img_ext = IOS_IMG_EXTENSIONS if ms.is_ios else IMG_EXTENSIONS
    current_files = dedup_media_dict(
        list_files(album_dir / ms.orig_img_dir), img_ext, ms.key_fn
    )
    current_keys = set(current_files.keys())
    processed_keys = set(state.processed_keys.keys())

    thumb_dir_path = thumbs_dir(album_dir, ms.name)

    return _SourceCheck(
        unprocessed=tuple(
            f"{ms.name}:{k}" for k in sorted(current_keys - processed_keys)
        ),
        stale_entries=tuple(
            f"{ms.name}:{k}" for k in sorted(processed_keys - current_keys)
        ),
        missing_thumbs=tuple(
            f"{ms.name}:{key}"
            for key in state.processed_keys
            if key in current_keys and not (thumb_dir_path / f"{key}.jpg").is_file()
        ),
        stale_thumbs=tuple(
            f"{ms.name}:{key}"
            for key, entry in state.processed_keys.items()
            if key in current_keys
            and (thumb_dir_path / f"{key}.jpg").is_file()
            and (album_dir / ms.orig_img_dir / entry.file_name).is_file()
            and (album_dir / ms.orig_img_dir / entry.file_name).stat().st_mtime
            != entry.mtime
        ),
        model_mismatch=(
            state.model_name != model_name or state.model_version != model_version
        ),
        npz_yaml_sync_errors=_check_npz_yaml_sync(album_dir, ms.name, state),
    )


def _check_npz_yaml_sync(
    album_dir: Path,
    ms_name: str,
    state: object,
) -> tuple[str, ...]:
    """Check .npz/.yaml consistency for a media source."""
    from ..faces.protocol import FaceProcessingState

    if not isinstance(state, FaceProcessingState):
        return ()

    face_data = load_face_data(album_dir, ms_name)
    if face_data is None:
        return ()

    npz_keys = set(face_data.keys)
    state_keys_with_faces = {
        k for k, v in state.processed_keys.items() if v.face_count > 0
    }

    return tuple(
        [
            *(
                [f"{ms_name}: .npz keys don't match .yaml processed-keys"]
                if npz_keys != state_keys_with_faces
                else []
            ),
            *(
                [f"{ms_name}: .npz array lengths inconsistent"]
                if not (
                    len(face_data.keys)
                    == len(face_data.face_indices)
                    == len(face_data.det_scores)
                    == face_data.bboxes.shape[0]
                    == face_data.landmarks.shape[0]
                    == face_data.embeddings.shape[0]
                )
                else []
            ),
        ]
    )
