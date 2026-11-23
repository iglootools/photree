"""
Gallery face manifest I/O — load/save manifest, clusters, and checksums.

A file that exists but cannot be read raises
:class:`~photree.foundation.metadata_io.InvalidMetadataError` rather than reading as
absent: a corrupt ``clusters.yaml`` treated as missing would trigger a silent
full re-cluster that mints fresh cluster UUIDs and loses every identity.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)
from photree.gallery.faces.clustering import save_faiss_index
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

if TYPE_CHECKING:
    import faiss


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


def load_clusters(gallery_dir: Path) -> FaceClusteringResult | None:
    """
    Read the gallery's face clusters, or ``None`` if they do not exist.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError` when the
    file is corrupt.
    """
    return _load_yaml(clusters_path(gallery_dir), FaceClusteringResult)


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


@dataclass(frozen=True)
class GalleryFaceState:
    """Everything a clustering refresh saves, which only makes sense together."""

    index: faiss.IndexFlatIP
    manifest: FaceManifest
    clusters: FaceClusteringResult
    checksums: AlbumFaceChecksums


def save_face_state(gallery_dir: Path, state: GalleryFaceState) -> None:
    """
    Save *state*'s four files so that an interrupted save keeps the previous ones.

    Each file is written beside its target first, then all are renamed into
    place, checksums last. Writing takes as long as the index is large, and an
    interruption then leaves the previous state whole, cluster IDs included;
    only one between the renames leaves a mix, which the next refresh detects
    and re-clusters.
    """
    writes: tuple[tuple[Path, Callable[[Path], None]], ...] = (
        (faiss_index_path(gallery_dir), lambda p: save_faiss_index(state.index, p)),
        (manifest_path(gallery_dir), lambda p: _save_yaml(p, state.manifest)),
        (clusters_path(gallery_dir), lambda p: _save_yaml(p, state.clusters)),
        (checksums_path(gallery_dir), lambda p: _save_yaml(p, state.checksums)),
    )
    for path, write in writes:
        write(_staging_path(path))
    for path, _ in writes:
        _staging_path(path).replace(path)


def _staging_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.tmp")


def compute_npz_checksum(npz_path: Path) -> str:
    """Return the SHA-256 hex digest of an ``.npz`` file."""
    h = hashlib.sha256()
    with Path(npz_path).open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
