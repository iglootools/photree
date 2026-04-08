"""Face data I/O — load/save ``.npz`` arrays and ``.yaml`` state files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from ...fsprotocol import PHOTREE_DIR
from .protocol import (
    EMBEDDING_DIM,
    FACES_DATA_SUFFIX,
    FACES_DIR,
    FACES_STATE_SUFFIX,
    THUMBS_DIR_SUFFIX,
    FaceProcessingState,
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def faces_dir(album_dir: Path) -> Path:
    """Return ``<album>/.photree/faces/``."""
    return album_dir / PHOTREE_DIR / FACES_DIR


def state_path(album_dir: Path, media_source_name: str) -> Path:
    """Return ``<album>/.photree/faces/{name}.yaml``."""
    return faces_dir(album_dir) / f"{media_source_name}{FACES_STATE_SUFFIX}"


def data_path(album_dir: Path, media_source_name: str) -> Path:
    """Return ``<album>/.photree/faces/{name}.npz``."""
    return faces_dir(album_dir) / f"{media_source_name}{FACES_DATA_SUFFIX}"


def thumbs_dir(album_dir: Path, media_source_name: str) -> Path:
    """Return ``<album>/.photree/faces/{name}-thumbs/``."""
    return faces_dir(album_dir) / f"{media_source_name}{THUMBS_DIR_SUFFIX}"


# ---------------------------------------------------------------------------
# Face data arrays (.npz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceData:
    """In-memory representation of per-media-source face detection results.

    All arrays have length ``N`` (total detected faces across all images).
    """

    keys: np.ndarray  # (N,) str — media key per face
    face_indices: np.ndarray  # (N,) int32 — 0-based face index within image
    det_scores: np.ndarray  # (N,) float32 — detection confidence
    bboxes: np.ndarray  # (N, 4) float32 — bounding boxes [x1, y1, x2, y2]
    landmarks: np.ndarray  # (N, 5, 2) float32 — 5-point landmarks
    embeddings: np.ndarray  # (N, 512) float32 — ArcFace embeddings

    @property
    def count(self) -> int:
        return len(self.keys)

    @staticmethod
    def empty() -> FaceData:
        """Return an empty :class:`FaceData` with zero faces."""
        return FaceData(
            keys=np.array([], dtype=object),
            face_indices=np.array([], dtype=np.int32),
            det_scores=np.array([], dtype=np.float32),
            bboxes=np.empty((0, 4), dtype=np.float32),
            landmarks=np.empty((0, 5, 2), dtype=np.float32),
            embeddings=np.empty((0, EMBEDDING_DIM), dtype=np.float32),
        )


def load_face_data(album_dir: Path, media_source_name: str) -> FaceData | None:
    """Load face data from ``.photree/faces/{name}.npz``, or ``None`` if missing."""
    path = data_path(album_dir, media_source_name)
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=True) as npz:
        return FaceData(
            keys=npz["keys"],
            face_indices=npz["face_indices"],
            det_scores=npz["det_scores"],
            bboxes=npz["bboxes"],
            landmarks=npz["landmarks"],
            embeddings=npz["embeddings"],
        )


def save_face_data(album_dir: Path, media_source_name: str, data: FaceData) -> None:
    """Write face data to ``.photree/faces/{name}.npz``."""
    path = data_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        keys=data.keys,
        face_indices=data.face_indices,
        det_scores=data.det_scores,
        bboxes=data.bboxes,
        landmarks=data.landmarks,
        embeddings=data.embeddings,
    )


# ---------------------------------------------------------------------------
# Processing state (.yaml)
# ---------------------------------------------------------------------------


def load_face_state(
    album_dir: Path, media_source_name: str
) -> FaceProcessingState | None:
    """Load processing state from ``.photree/faces/{name}.yaml``."""
    path = state_path(album_dir, media_source_name)
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return (
        FaceProcessingState.model_validate(raw) if isinstance(raw, dict) else None
    )


def save_face_state(
    album_dir: Path, media_source_name: str, state: FaceProcessingState
) -> None:
    """Write processing state to ``.photree/faces/{name}.yaml``."""
    path = state_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            state.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )


# ---------------------------------------------------------------------------
# Merge / filter helpers
# ---------------------------------------------------------------------------


def filter_face_data(data: FaceData, *, keep_keys: set[str]) -> FaceData:
    """Return a new :class:`FaceData` containing only faces whose key is in *keep_keys*."""
    if data.count == 0:
        return data
    mask = np.isin(data.keys, list(keep_keys))
    return FaceData(
        keys=data.keys[mask],
        face_indices=data.face_indices[mask],
        det_scores=data.det_scores[mask],
        bboxes=data.bboxes[mask],
        landmarks=data.landmarks[mask],
        embeddings=data.embeddings[mask],
    )


def merge_face_data(existing: FaceData, new: FaceData) -> FaceData:
    """Concatenate two :class:`FaceData` instances."""
    if existing.count == 0:
        return new
    if new.count == 0:
        return existing
    return FaceData(
        keys=np.concatenate([existing.keys, new.keys]),
        face_indices=np.concatenate([existing.face_indices, new.face_indices]),
        det_scores=np.concatenate([existing.det_scores, new.det_scores]),
        bboxes=np.concatenate([existing.bboxes, new.bboxes]),
        landmarks=np.concatenate([existing.landmarks, new.landmarks]),
        embeddings=np.concatenate([existing.embeddings, new.embeddings]),
    )
