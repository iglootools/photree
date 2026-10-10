"""Face state validation — verify face data consistency with album contents.

During check, the face state is trusted without per-file mtime
verification. The state is validated at write time during album refresh.
Use ``album refresh --redetect-faces`` to force re-detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..faces.protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessingState,
)
from ..faces.store import (
    FaceData,
    data_path,
    load_face_data,
    load_face_state,
    state_path,
)
from ..store.media_source import MediaSource


class FaceSyncIssueKind(StrEnum):
    # Refresh writes the .npz and the .yaml together, so one without the
    # other means a write was interrupted or a file was deleted by hand.
    MISSING_NPZ = "missing-npz"  # .yaml records faces, .npz is absent
    MISSING_YAML = "missing-yaml"  # .npz present, .yaml is absent
    KEYS_MISMATCH = "keys-mismatch"  # .npz keys != .yaml keys with faces
    ARRAY_LENGTHS = "array-lengths"  # .npz arrays of different lengths


@dataclass(frozen=True)
class FaceSyncIssue:
    """A .npz/.yaml inconsistency for one media source."""

    media_source: str
    kind: FaceSyncIssueKind


@dataclass(frozen=True)
class FaceStateCheck:
    """Result of face state validation for an album."""

    model_mismatch: bool
    npz_yaml_sync_errors: tuple[FaceSyncIssue, ...]

    @property
    def success(self) -> bool:
        return not self.model_mismatch and len(self.npz_yaml_sync_errors) == 0

    @property
    def issue_count(self) -> int:
        return (1 if self.model_mismatch else 0) + len(self.npz_yaml_sync_errors)


def check_face_state(
    album_dir: Path,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str = DEFAULT_MODEL_VERSION,
    media_sources: list[MediaSource],
) -> FaceStateCheck | None:
    """Validate face detection state for an album.

    Returns ``None`` if no face data exists. Trusts the state without
    per-file mtime verification — the state is validated at write time
    during album refresh.
    """
    has_any_face_data = any(
        state_path(album_dir, ms.name).is_file()
        or data_path(album_dir, ms.name).is_file()
        for ms in media_sources
    )
    if not has_any_face_data:
        return None
    else:
        per_source = [
            _check_source(
                album_dir, ms, model_name=model_name, model_version=model_version
            )
            for ms in media_sources
        ]
        return FaceStateCheck(
            model_mismatch=any(r.model_mismatch for r in per_source),
            npz_yaml_sync_errors=tuple(
                s for r in per_source for s in r.npz_yaml_sync_errors
            ),
        )


# ---------------------------------------------------------------------------
# Per-source check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SourceCheck:
    model_mismatch: bool
    npz_yaml_sync_errors: tuple[FaceSyncIssue, ...]


def _check_source(
    album_dir: Path,
    ms: MediaSource,
    *,
    model_name: str,
    model_version: str,
) -> _SourceCheck:
    """Validate face state for a single media source."""
    state = load_face_state(album_dir, ms.name)
    face_data = load_face_data(album_dir, ms.name)
    match (state, face_data):
        case (None, None):
            return _SourceCheck(model_mismatch=False, npz_yaml_sync_errors=())
        case (None, FaceData()):
            return _SourceCheck(
                model_mismatch=False,
                npz_yaml_sync_errors=(
                    FaceSyncIssue(ms.name, FaceSyncIssueKind.MISSING_YAML),
                ),
            )
        case (FaceProcessingState() as s, _):
            return _SourceCheck(
                model_mismatch=(
                    s.model_name != model_name or s.model_version != model_version
                ),
                npz_yaml_sync_errors=_check_npz_yaml_sync(ms.name, s, face_data),
            )


# ---------------------------------------------------------------------------
# .npz / .yaml sync check
# ---------------------------------------------------------------------------


def _check_npz_yaml_sync(
    ms_name: str,
    state: FaceProcessingState,
    face_data: FaceData | None,
) -> tuple[FaceSyncIssue, ...]:
    """Check .npz/.yaml consistency for a media source with a .yaml state."""
    state_keys_with_faces = {
        k for k, v in state.processed_keys.items() if v.face_count > 0
    }
    match face_data:
        case None:
            # No faces recorded means there is nothing the .npz should hold.
            return (
                (FaceSyncIssue(ms_name, FaceSyncIssueKind.MISSING_NPZ),)
                if state_keys_with_faces
                else ()
            )
        case data:
            return (
                *(
                    [FaceSyncIssue(ms_name, FaceSyncIssueKind.KEYS_MISMATCH)]
                    if set(data.keys) != state_keys_with_faces
                    else []
                ),
                *(
                    [FaceSyncIssue(ms_name, FaceSyncIssueKind.ARRAY_LENGTHS)]
                    if not _consistent_lengths(data)
                    else []
                ),
            )


def _consistent_lengths(data: FaceData) -> bool:
    return (
        len(data.keys)
        == len(data.face_indices)
        == len(data.det_scores)
        == data.bboxes.shape[0]
        == data.landmarks.shape[0]
        == data.embeddings.shape[0]
    )
