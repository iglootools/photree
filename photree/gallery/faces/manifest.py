"""
Gallery face manifest I/O — load/save manifest, clusters, and checksums.

A file that exists but cannot be read raises
:class:`~photree.foundation.metadata_io.InvalidMetadataError` rather than reading as
absent: a corrupt ``clusters.yaml`` treated as missing would trigger a silent
full re-cluster that mints fresh cluster UUIDs and loses every identity.
"""

import hashlib
from pathlib import Path

from pydantic import BaseModel

from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)
from photree.gallery.faces.protocol import (
    FACE_CHECKSUMS_FILE,
    FACE_CLUSTERS_FILE,
    FACE_INDEX_FILE,
    FACE_MANIFEST_FILE,
    FACES_DIR,
    AlbumFaceChecksums,
    FaceClusteringResult,
    FaceManifest,
)


def gallery_faces_dir(gallery_dir: Path) -> Path:
    """Return ``<gallery>/.photree/faces/``."""
    return gallery_dir / PHOTREE_DIR / FACES_DIR


def manifest_path(gallery_dir: Path) -> Path:
    """Return the path of the gallery's face manifest file."""
    return gallery_faces_dir(gallery_dir) / FACE_MANIFEST_FILE


def clusters_path(gallery_dir: Path) -> Path:
    """Return the path of the gallery's face clusters file."""
    return gallery_faces_dir(gallery_dir) / FACE_CLUSTERS_FILE


def checksums_path(gallery_dir: Path) -> Path:
    """Return the path of the gallery's per-album face checksums file."""
    return gallery_faces_dir(gallery_dir) / FACE_CHECKSUMS_FILE


def faiss_index_path(gallery_dir: Path) -> Path:
    """Return the path of the gallery's FAISS face index file."""
    return gallery_faces_dir(gallery_dir) / FACE_INDEX_FILE


def _load_yaml[M: BaseModel](path: Path, model_cls: type[M]) -> M | None:
    """Load *path* as *model_cls*, or ``None`` when the file does not exist."""
    raw = load_yaml_mapping(path)
    return validate_metadata(path, model_cls, raw) if raw is not None else None


def _save_yaml(path: Path, model: BaseModel) -> None:
    """Save a Pydantic model to YAML (kebab-case aliases)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, model.model_dump(by_alias=True, mode="json"))


def load_manifest(gallery_dir: Path) -> FaceManifest | None:
    """
    Read the gallery's face manifest, or ``None`` if it does not exist.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError` when it is
    corrupt.
    """
    return _load_yaml(manifest_path(gallery_dir), FaceManifest)


def save_manifest(gallery_dir: Path, manifest: FaceManifest) -> None:
    """Write *manifest* as the gallery's face manifest, creating its directory."""
    _save_yaml(manifest_path(gallery_dir), manifest)


def load_clusters(gallery_dir: Path) -> FaceClusteringResult | None:
    """
    Read the gallery's face clusters, or ``None`` if they do not exist.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError` when the
    file is corrupt.
    """
    return _load_yaml(clusters_path(gallery_dir), FaceClusteringResult)


def save_clusters(gallery_dir: Path, result: FaceClusteringResult) -> None:
    """Write *result* as the gallery's face clusters, creating its directory."""
    _save_yaml(clusters_path(gallery_dir), result)


def load_checksums(gallery_dir: Path) -> AlbumFaceChecksums | None:
    """
    Read the gallery's per-album face checksums, or ``None`` if they do not exist.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError` when the
    file is corrupt.
    """
    return _load_yaml(checksums_path(gallery_dir), AlbumFaceChecksums)


def save_checksums(gallery_dir: Path, checksums: AlbumFaceChecksums) -> None:
    """Write *checksums* as the gallery's per-album face checksums, making its dir."""
    _save_yaml(checksums_path(gallery_dir), checksums)


def compute_npz_checksum(npz_path: Path) -> str:
    """Return the SHA-256 hex digest of an ``.npz`` file."""
    h = hashlib.sha256()
    with Path(npz_path).open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
