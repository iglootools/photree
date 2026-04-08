"""Gallery face manifest I/O — load/save manifest, clusters, and checksums."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from ...fsprotocol import PHOTREE_DIR
from .protocol import (
    FACE_CHECKSUMS_FILE,
    FACE_CLUSTERS_FILE,
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
    from .protocol import FACE_INDEX_FILE

    return gallery_faces_dir(gallery_dir) / FACE_INDEX_FILE


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


def _load_yaml(path: Path, model_cls: type):  # type: ignore[type-arg]
    """Load and validate a YAML file against a Pydantic model."""
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return model_cls.model_validate(raw) if isinstance(raw, dict) else None


def _save_yaml(path: Path, model: object) -> None:
    """Save a Pydantic model to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            model.model_dump(by_alias=True, mode="json"),  # type: ignore[union-attr]
            default_flow_style=False,
            sort_keys=False,
        )
    )


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
