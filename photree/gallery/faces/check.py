"""Gallery face cluster consistency checks.

Pure validation of the gallery-level face data against itself (cluster indices
vs. manifest) and against the per-album face caches (checksums). Returns
structured issues; the CLI layer renders them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...album.faces.protocol import FACES_DIR
from ...album.store.album_discovery import discover_albums
from ...album.store.metadata import load_album_metadata
from ...foundation.layout import ALBUMS_DIR, PHOTREE_DIR
from .manifest import compute_npz_checksum, load_checksums, load_clusters, load_manifest
from .protocol import FaceClusteringResult


@dataclass(frozen=True)
class ClusterIndexOutOfBounds:
    """A cluster references face indices past the end of the manifest."""

    cluster_id: str
    count: int


@dataclass(frozen=True)
class FaceCountMismatch:
    """``clusters.yaml`` records a face count the manifest does not have."""

    recorded: int
    manifest_size: int


@dataclass(frozen=True)
class AlbumFaceDataNotIndexed:
    """An album's face data was never ingested into the gallery index."""

    album_dir: Path
    media_source: str


@dataclass(frozen=True)
class AlbumFaceDataChanged:
    """An album's face data changed since the gallery index ingested it."""

    album_dir: Path
    media_source: str


type FaceClusterIssue = (
    ClusterIndexOutOfBounds
    | FaceCountMismatch
    | AlbumFaceDataNotIndexed
    | AlbumFaceDataChanged
)


@dataclass(frozen=True)
class FaceClusterCheck:
    """Outcome of :func:`check_face_clusters`."""

    clusters: FaceClusteringResult
    issues: tuple[FaceClusterIssue, ...]

    @property
    def success(self) -> bool:
        return not self.issues


def check_face_clusters(gallery_dir: Path) -> FaceClusterCheck | None:
    """Validate face cluster consistency, or ``None`` if nothing was clustered."""
    manifest = load_manifest(gallery_dir)
    clusters = load_clusters(gallery_dir)
    if manifest is None or clusters is None:
        return None
    manifest_size = len(manifest.faces)
    return FaceClusterCheck(
        clusters=clusters,
        issues=(
            *_index_bounds_issues(clusters, manifest_size),
            *_face_count_issues(clusters, manifest_size),
            *_album_checksum_issues(gallery_dir),
        ),
    )


def _index_bounds_issues(
    clusters: FaceClusteringResult, manifest_size: int
) -> list[FaceClusterIssue]:
    """Clusters whose face indices fall outside the manifest."""
    return [
        ClusterIndexOutOfBounds(cluster_id=cluster.id, count=oob)
        for cluster in clusters.clusters
        for oob in [
            sum(1 for idx in cluster.face_indices if idx < 0 or idx >= manifest_size)
        ]
        if oob
    ]


def _face_count_issues(
    clusters: FaceClusteringResult, manifest_size: int
) -> list[FaceClusterIssue]:
    """``clusters.face_count`` disagreeing with the manifest size."""
    return (
        [FaceCountMismatch(recorded=clusters.face_count, manifest_size=manifest_size)]
        if clusters.face_count != manifest_size
        else []
    )


def _album_checksum_issues(gallery_dir: Path) -> list[FaceClusterIssue]:
    """Album face data missing from, or changed since, the gallery index."""
    stored = load_checksums(gallery_dir)
    if stored is None:
        return []
    return [
        issue
        for album_dir in discover_albums(gallery_dir / ALBUMS_DIR)
        for issue in _single_album_issues(album_dir, stored.albums)
    ]


def _single_album_issues(
    album_dir: Path, stored_albums: dict[str, dict[str, str]]
) -> list[FaceClusterIssue]:
    meta = load_album_metadata(album_dir)
    faces_dir = album_dir / PHOTREE_DIR / FACES_DIR
    if meta is None or not faces_dir.is_dir():
        return []
    album_checksums = stored_albums.get(meta.id, {})
    return [
        issue
        for npz_file in sorted(faces_dir.glob("*.npz"))
        for issue in [_checksum_issue(album_dir, npz_file, album_checksums)]
        if issue is not None
    ]


def _checksum_issue(
    album_dir: Path, npz_file: Path, album_checksums: dict[str, str]
) -> FaceClusterIssue | None:
    match album_checksums.get(npz_file.stem):
        case None:
            return AlbumFaceDataNotIndexed(album_dir, npz_file.stem)
        case ck if ck != compute_npz_checksum(npz_file):
            return AlbumFaceDataChanged(album_dir, npz_file.stem)
        case _:
            return None
