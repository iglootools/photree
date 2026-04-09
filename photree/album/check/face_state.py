"""Face state validation — verify face data consistency with album contents.

During check, the face state is trusted without per-file mtime
verification. The state is validated at write time during album refresh.
Use ``album refresh --redetect-faces`` to force re-detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..faces.protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessingState,
)
from ..faces.store import (
    data_path,
    load_face_data,
    load_face_state,
    state_path,
)
from ..store.protocol import MediaSource


@dataclass(frozen=True)
class FaceStateCheck:
    """Result of face state validation for an album."""

    model_mismatch: bool
    npz_yaml_sync_errors: tuple[str, ...]

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
    npz_yaml_sync_errors: tuple[str, ...]


_EMPTY = _SourceCheck(model_mismatch=False, npz_yaml_sync_errors=())


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
        return _EMPTY

    return _SourceCheck(
        model_mismatch=(
            state.model_name != model_name or state.model_version != model_version
        ),
        npz_yaml_sync_errors=_check_npz_yaml_sync(album_dir, ms.name, state),
    )


# ---------------------------------------------------------------------------
# .npz / .yaml sync check
# ---------------------------------------------------------------------------


def _check_npz_yaml_sync(
    album_dir: Path,
    ms_name: str,
    state: FaceProcessingState,
) -> tuple[str, ...]:
    """Check .npz/.yaml consistency for a media source."""
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
