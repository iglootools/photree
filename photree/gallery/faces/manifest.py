"""Gallery face manifest I/O — load/save manifest, clusters, and checksums.

A file that exists but cannot be read raises
:class:`~photree.foundation.metadata_io.InvalidMetadataError` rather than reading as
absent: a corrupt ``clusters.yaml`` treated as missing would trigger a silent
full re-cluster that mints fresh cluster UUIDs and loses every identity.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel

from ...foundation.layout import PHOTREE_DIR
from ...foundation.metadata_io import load_yaml_mapping, validate_metadata, write_yaml
from .protocol import (
    FACE_CHECKSUMS_FILE,
    FACE_CLUSTERS_FILE,
    FACE_INDEX_FILE,
    FACE_MANIFEST_FILE,
    FACES_DIR,
    AlbumFaceChecksums,
    FaceClusteringResult,
    FaceManifest,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def gallery_faces_dir(gallery_dir: Path) -> Path:
    """Return ``<gallery>/.photree/faces/``."""
    return gallery_dir / PHOTREE_DIR / FACES_DIR


def manifest_path(gallery_dir: Path) -> Path:
    return gallery_faces_dir(gallery_dir) / FACE_MANIFEST_FILE


def clusters_path(gallery_dir: Path) -> Path:
    return gallery_faces_dir(gallery_dir) / FACE_CLUSTERS_FILE


def checksums_path(gallery_dir: Path) -> Path:
    return gallery_faces_dir(gallery_dir) / FACE_CHECKSUMS_FILE


def faiss_index_path(gallery_dir: Path) -> Path:
    return gallery_faces_dir(gallery_dir) / FACE_INDEX_FILE


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


def _load_yaml[M: BaseModel](path: Path, model_cls: type[M]) -> M | None:
    """Load *path* as *model_cls*, or ``None`` when the file does not exist."""
    raw = load_yaml_mapping(path)
    return validate_metadata(path, model_cls, raw) if raw is not None else None


def _save_yaml(path: Path, model: BaseModel) -> None:
    """Save a Pydantic model to YAML (kebab-case aliases)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, model.model_dump(by_alias=True, mode="json"))


def load_manifest(gallery_dir: Path) -> FaceManifest | None:
    return _load_yaml(manifest_path(gallery_dir), FaceManifest)


def save_manifest(gallery_dir: Path, manifest: FaceManifest) -> None:
    _save_yaml(manifest_path(gallery_dir), manifest)


def load_clusters(gallery_dir: Path) -> FaceClusteringResult | None:
    return _load_yaml(clusters_path(gallery_dir), FaceClusteringResult)


def save_clusters(gallery_dir: Path, result: FaceClusteringResult) -> None:
    _save_yaml(clusters_path(gallery_dir), result)


def load_checksums(gallery_dir: Path) -> AlbumFaceChecksums | None:
    return _load_yaml(checksums_path(gallery_dir), AlbumFaceChecksums)


def save_checksums(gallery_dir: Path, checksums: AlbumFaceChecksums) -> None:
    _save_yaml(checksums_path(gallery_dir), checksums)


# ---------------------------------------------------------------------------
# Checksum computation
# ---------------------------------------------------------------------------


def compute_npz_checksum(npz_path: Path) -> str:
    """Return the SHA-256 hex digest of an ``.npz`` file."""
    h = hashlib.sha256()
    with open(npz_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
