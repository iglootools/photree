"""InsightFace wrapper — face detection, alignment, and embedding extraction.

Handles thumbnail generation via ``sips`` and feeds resized JPEGs to
InsightFace for analysis. Supports CoreML execution provider on M-series
Macs for Neural Engine acceleration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from ...common.sips import get_dimensions, resize_to_jpeg
from .protocol import DEFAULT_MODEL_NAME, THUMB_MAX_DIMENSION


# ---------------------------------------------------------------------------
# InsightFace model management
# ---------------------------------------------------------------------------


def create_face_analyzer(
    model_name: str = DEFAULT_MODEL_NAME,
) -> FaceAnalysis:
    """Create and prepare an InsightFace :class:`FaceAnalysis` instance.

    Prefers ``CoreMLExecutionProvider`` (M-series Neural Engine) with
    fallback to ``CPUExecutionProvider``.
    """
    app = FaceAnalysis(
        name=model_name,
        providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


# ---------------------------------------------------------------------------
# Thumbnail generation via sips
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThumbnailResult:
    """Result of generating a thumbnail for one image."""

    key: str
    file_name: str
    thumb_path: Path
    orig_width: int
    orig_height: int
    thumb_width: int
    thumb_height: int


def generate_thumbnail(
    key: str,
    file_name: str,
    src: Path,
    dst: Path,
    *,
    max_dimension: int = THUMB_MAX_DIMENSION,
) -> ThumbnailResult:
    """Generate a resized JPEG thumbnail via ``sips``.

    Returns a :class:`ThumbnailResult` with original and thumbnail dimensions.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Read original dimensions before resize
    orig_width, orig_height = get_dimensions(src)

    # Convert + resize to JPEG thumbnail
    resize_to_jpeg(src, dst, max_dimension=max_dimension)

    # Read actual thumbnail dimensions (may differ due to aspect ratio)
    thumb_width, thumb_height = get_dimensions(dst)

    return ThumbnailResult(
        key=key,
        file_name=file_name,
        thumb_path=dst,
        orig_width=orig_width,
        orig_height=orig_height,
        thumb_width=thumb_width,
        thumb_height=thumb_height,
    )


# ---------------------------------------------------------------------------
# Face analysis on a single image
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectedFace:
    """A single detected face from one image."""

    key: str
    face_index: int
    det_score: float
    bbox: np.ndarray  # (4,) float32
    landmarks: np.ndarray  # (5, 2) float32
    embedding: np.ndarray  # (512,) float32


def detect_faces(
    key: str,
    image_path: Path,
    analyzer: FaceAnalysis,
) -> list[DetectedFace]:
    """Run InsightFace on a single image, returning detected faces.

    Returns an empty list when no faces are found or the image cannot be read.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return []

    faces = analyzer.get(img)

    return [
        DetectedFace(
            key=key,
            face_index=i,
            det_score=float(face.det_score),
            bbox=face.bbox.astype(np.float32),
            landmarks=face.landmark_2d_106[:5].astype(np.float32)
            if hasattr(face, "landmark_2d_106") and face.landmark_2d_106 is not None
            else face.kps.astype(np.float32)
            if hasattr(face, "kps") and face.kps is not None
            else np.zeros((5, 2), dtype=np.float32),
            embedding=face.normed_embedding.astype(np.float32)
            if hasattr(face, "normed_embedding")
            else face.embedding.astype(np.float32),
        )
        for i, face in enumerate(faces)
        if hasattr(face, "embedding") and face.embedding is not None
    ]


# ---------------------------------------------------------------------------
# Thumbnail path helpers
# ---------------------------------------------------------------------------


def thumb_filename(key: str) -> str:
    """Return the thumbnail filename for a media key (e.g. ``"0410.jpg"``)."""
    return f"{key}.jpg"
