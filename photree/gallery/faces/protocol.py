"""Gallery face clustering protocol — models and constants."""

from __future__ import annotations

from pydantic import Field

from ...fsprotocol import _BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FACES_DIR = "faces"
"""Subdirectory under gallery ``.photree/`` for face clustering data."""

FACE_INDEX_FILE = "face-index.faiss"
FACE_MANIFEST_FILE = "face-manifest.yaml"
FACE_CLUSTERS_FILE = "clusters.yaml"
FACE_CHECKSUMS_FILE = "album-checksums.yaml"

DEFAULT_CLUSTER_THRESHOLD = 0.45
"""Default cosine distance threshold for face clustering."""


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FaceReference(_BaseModel):
    """A reference to a single detected face in the gallery."""

    album_id: str = Field(description="Album internal UUID.")
    media_source: str = Field(description="Media source name (e.g. 'main').")
    media_key: str = Field(description="Media key (image number or filename stem).")
    face_index: int = Field(description="0-based face index within the image.")


class FaceManifest(_BaseModel):
    """Maps FAISS index rows to face references.

    Position ``i`` in ``faces`` corresponds to row ``i`` in the FAISS index.
    """

    faces: list[FaceReference] = Field(default_factory=list)


class FaceCluster(_BaseModel):
    """A cluster of faces belonging to the same identity."""

    id: str = Field(description="UUID v7 for stable identity across re-clusters.")
    face_indices: list[int] = Field(
        default_factory=list,
        description="Indices into FaceManifest.faces.",
    )


class FaceClusteringResult(_BaseModel):
    """Persistent clustering result stored in ``clusters.yaml``."""

    version: int = Field(default=1)
    threshold: float = Field(description="Cosine distance threshold used.")
    face_count: int = Field(default=0)
    cluster_count: int = Field(default=0)
    clusters: list[FaceCluster] = Field(default_factory=list)


class AlbumFaceChecksums(_BaseModel):
    """Tracks which album face data has been ingested into the gallery index.

    Maps ``album_id → {media_source → sha256_hex}``.
    """

    albums: dict[str, dict[str, str]] = Field(default_factory=dict)
