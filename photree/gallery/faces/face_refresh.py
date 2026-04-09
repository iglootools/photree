"""Gallery-level face clustering refresh — scan, index, cluster, save."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from uuid6 import uuid7

from ...album.faces.protocol import FACES_DIR
from ...album.faces.store import load_face_data
from ...album.store.album_discovery import discover_albums
from ...album.store.metadata import load_album_metadata
from ...albums.index import AlbumIndex, build_album_index
from ...fsprotocol import ALBUMS_DIR, PHOTREE_DIR
from .clustering import (
    assign_to_nearest_cluster,
    build_faiss_index,
    cluster_embeddings,
    load_faiss_index,
    match_clusters_by_medoid,
    save_faiss_index,
)
from .manifest import (
    compute_npz_checksum,
    faiss_index_path,
    load_checksums,
    load_clusters,
    load_manifest,
    save_checksums,
    save_clusters,
    save_manifest,
)
from .protocol import (
    DEFAULT_CLUSTER_THRESHOLD,
    AlbumFaceChecksums,
    FaceCluster,
    FaceClusteringResult,
    FaceManifest,
    FaceReference,
)

# ---------------------------------------------------------------------------
# Stage constants
# ---------------------------------------------------------------------------

STAGE_SCAN_FACE_DATA = "scan-face-data"
STAGE_BUILD_INDEX = "build-index"
STAGE_CLUSTER = "cluster-faces"
STAGE_SAVE = "save-results"

FACE_REFRESH_STAGES = (
    STAGE_SCAN_FACE_DATA,
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceRefreshError:
    message: str


@dataclass(frozen=True)
class GalleryFaceRefreshResult:
    """Result of a gallery face clustering refresh."""

    total_faces: int = 0
    total_clusters: int = 0
    new_faces: int = 0
    removed_faces: int = 0
    mode: str = "none"  # "incremental", "full", "none"
    errors: tuple[FaceRefreshError, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AlbumFaceSource:
    album_id: str
    media_source: str
    npz_path: Path
    checksum: str


@dataclass(frozen=True)
class _ChangeSet:
    new_sources: list[_AlbumFaceSource]
    modified_sources: list[_AlbumFaceSource]
    removed_album_sources: list[tuple[str, str]]  # (album_id, media_source)
    unchanged_sources: list[_AlbumFaceSource]


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def refresh_face_clusters(
    gallery_dir: Path,
    *,
    distance_threshold: float | None = None,
    dry_run: bool = False,
    force_full: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> GalleryFaceRefreshResult:
    """Refresh face clustering for the entire gallery.

    Collects face embeddings from all albums, builds/updates the FAISS index,
    and runs clustering (incremental or full).
    """
    threshold = distance_threshold or DEFAULT_CLUSTER_THRESHOLD

    # ── Stage 1: scan-face-data ──
    _notify(on_stage_start, STAGE_SCAN_FACE_DATA)
    albums_dir = gallery_dir / ALBUMS_DIR
    album_dirs = discover_albums(albums_dir)
    album_index = build_album_index(album_dirs)

    existing_checksums = load_checksums(gallery_dir) or AlbumFaceChecksums()
    changes = _compute_changes(album_dirs, album_index, existing_checksums)
    _notify(on_stage_end, STAGE_SCAN_FACE_DATA)

    has_changes = (
        changes.new_sources or changes.modified_sources or changes.removed_album_sources
    )

    if not has_changes and not force_full:
        _notify(on_stage_start, STAGE_BUILD_INDEX)
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        _notify(on_stage_start, STAGE_CLUSTER)
        _notify(on_stage_end, STAGE_CLUSTER)
        _notify(on_stage_start, STAGE_SAVE)
        _notify(on_stage_end, STAGE_SAVE)

        existing_clusters = load_clusters(gallery_dir)
        return GalleryFaceRefreshResult(
            total_faces=existing_clusters.face_count if existing_clusters else 0,
            total_clusters=existing_clusters.cluster_count if existing_clusters else 0,
            mode="none",
        )

    # Determine mode
    needs_full = (
        force_full
        or bool(changes.modified_sources)
        or bool(changes.removed_album_sources)
    )

    # Check if threshold changed
    existing_clusters = load_clusters(gallery_dir)
    if existing_clusters is not None and existing_clusters.threshold != threshold:
        needs_full = True

    if dry_run:
        new_count = sum(_count_faces(s.npz_path) for s in changes.new_sources)
        _notify(on_stage_start, STAGE_BUILD_INDEX)
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        _notify(on_stage_start, STAGE_CLUSTER)
        _notify(on_stage_end, STAGE_CLUSTER)
        _notify(on_stage_start, STAGE_SAVE)
        _notify(on_stage_end, STAGE_SAVE)
        return GalleryFaceRefreshResult(
            new_faces=new_count,
            mode="full" if needs_full else "incremental",
        )

    if needs_full:
        return _run_full_cluster(
            gallery_dir,
            changes,
            album_index,
            threshold=threshold,
            existing_clusters=existing_clusters,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
        )
    else:
        return _run_incremental(
            gallery_dir,
            changes,
            threshold=threshold,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
        )


# ---------------------------------------------------------------------------
# Full re-cluster
# ---------------------------------------------------------------------------


def _run_full_cluster(
    gallery_dir: Path,
    changes: _ChangeSet,
    album_index: AlbumIndex,
    *,
    threshold: float,
    existing_clusters: FaceClusteringResult | None,
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
) -> GalleryFaceRefreshResult:
    """Rebuild the FAISS index and re-cluster everything."""
    # Collect all face data from all album sources
    all_sources = [
        *changes.new_sources,
        *changes.modified_sources,
        *changes.unchanged_sources,
    ]

    # ── Stage 2: build-index ──
    _notify(on_stage_start, STAGE_BUILD_INDEX)
    all_refs: list[FaceReference] = []
    all_embeddings: list[np.ndarray] = []

    for src in all_sources:
        data = load_face_data(src.npz_path.parent.parent.parent, src.media_source)
        if data is None or data.count == 0:
            continue
        for i in range(data.count):
            all_refs.append(
                FaceReference(
                    album_id=src.album_id,
                    media_source=src.media_source,
                    media_key=str(data.keys[i]),
                    face_index=int(data.face_indices[i]),
                )
            )
        all_embeddings.append(data.embeddings)

    if not all_embeddings:
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        _notify(on_stage_start, STAGE_CLUSTER)
        _notify(on_stage_end, STAGE_CLUSTER)
        _notify(on_stage_start, STAGE_SAVE)
        _save_empty(gallery_dir, all_sources, threshold)
        _notify(on_stage_end, STAGE_SAVE)
        return GalleryFaceRefreshResult(mode="full")

    embeddings = np.concatenate(all_embeddings, axis=0).astype(np.float32)
    index = build_faiss_index(embeddings)
    _notify(on_stage_end, STAGE_BUILD_INDEX)

    # ── Stage 3: cluster ──
    _notify(on_stage_start, STAGE_CLUSTER)
    labels = cluster_embeddings(embeddings, distance_threshold=threshold)

    # Medoid matching: preserve old cluster UUIDs where possible
    old_label_to_uuid: dict[int, str] = {}
    if existing_clusters is not None:
        old_manifest = load_manifest(gallery_dir)
        old_index = load_faiss_index(faiss_index_path(gallery_dir))
        if old_manifest and old_index and old_index.ntotal > 0:
            old_embeddings = np.zeros((old_index.ntotal, old_index.d), dtype=np.float32)
            old_index.reconstruct_n(0, old_index.ntotal, old_embeddings)
            old_labels = _labels_from_clusters(existing_clusters, old_manifest)
            old_id_map = {
                i: c.id
                for c in existing_clusters.clusters
                for i in [_cluster_label_for(c, old_labels)]
                if i is not None
            }
            matched = match_clusters_by_medoid(
                old_embeddings,
                old_labels,
                old_id_map,
                embeddings,
                labels,
                threshold=threshold,
            )
            old_label_to_uuid = matched

    # Assign UUIDs to clusters
    cluster_map = _assign_cluster_uuids(labels, old_label_to_uuid)
    _notify(on_stage_end, STAGE_CLUSTER)

    # ── Stage 4: save ──
    _notify(on_stage_start, STAGE_SAVE)
    manifest = FaceManifest(faces=all_refs)
    clusters = [
        FaceCluster(
            id=uuid_str,
            face_indices=sorted(int(idx) for idx in np.where(labels == label)[0]),
        )
        for label, uuid_str in sorted(cluster_map.items())
    ]
    result = FaceClusteringResult(
        threshold=threshold,
        face_count=len(embeddings),
        cluster_count=len(clusters),
        clusters=clusters,
    )

    save_faiss_index(index, faiss_index_path(gallery_dir))
    save_manifest(gallery_dir, manifest)
    save_clusters(gallery_dir, result)
    save_checksums(
        gallery_dir,
        _build_checksums(all_sources),
    )
    _notify(on_stage_end, STAGE_SAVE)

    return GalleryFaceRefreshResult(
        total_faces=len(embeddings),
        total_clusters=len(clusters),
        new_faces=sum(_count_faces(s.npz_path) for s in changes.new_sources),
        removed_faces=0,
        mode="full",
    )


# ---------------------------------------------------------------------------
# Incremental assignment
# ---------------------------------------------------------------------------


def _run_incremental(
    gallery_dir: Path,
    changes: _ChangeSet,
    *,
    threshold: float,
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
) -> GalleryFaceRefreshResult:
    """Add new faces to the existing index and assign to nearest cluster."""
    # ── Stage 2: build-index ──
    _notify(on_stage_start, STAGE_BUILD_INDEX)
    index = load_faiss_index(faiss_index_path(gallery_dir))
    manifest = load_manifest(gallery_dir) or FaceManifest()
    existing_clusters_result = load_clusters(gallery_dir)

    if index is None:
        # No existing index — fall back to full mode
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        all_sources = [*changes.new_sources, *changes.unchanged_sources]
        return _run_full_cluster(
            gallery_dir,
            changes,
            AlbumIndex(id_to_path={}, duplicates={}),
            threshold=threshold,
            existing_clusters=existing_clusters_result,
            on_stage_start=lambda _: None,
            on_stage_end=lambda _: None,
        )

    # Collect new face data
    new_refs: list[FaceReference] = []
    new_embeddings_list: list[np.ndarray] = []

    for src in changes.new_sources:
        album_dir = src.npz_path.parent.parent.parent
        data = load_face_data(album_dir, src.media_source)
        if data is None or data.count == 0:
            continue
        for i in range(data.count):
            new_refs.append(
                FaceReference(
                    album_id=src.album_id,
                    media_source=src.media_source,
                    media_key=str(data.keys[i]),
                    face_index=int(data.face_indices[i]),
                )
            )
        new_embeddings_list.append(data.embeddings)

    if not new_embeddings_list:
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        _notify(on_stage_start, STAGE_CLUSTER)
        _notify(on_stage_end, STAGE_CLUSTER)
        _notify(on_stage_start, STAGE_SAVE)
        _notify(on_stage_end, STAGE_SAVE)
        return GalleryFaceRefreshResult(
            total_faces=index.ntotal,
            total_clusters=(
                existing_clusters_result.cluster_count
                if existing_clusters_result
                else 0
            ),
            mode="incremental",
        )

    new_embeddings = np.concatenate(new_embeddings_list, axis=0).astype(np.float32)

    # Build labels array from existing clusters
    existing_labels = (
        _labels_from_clusters(existing_clusters_result, manifest)
        if existing_clusters_result
        else np.array([], dtype=np.int32)
    )

    _notify(on_stage_end, STAGE_BUILD_INDEX)

    # ── Stage 3: cluster ──
    _notify(on_stage_start, STAGE_CLUSTER)
    max_existing_label = (
        int(existing_labels.max()) + 1 if len(existing_labels) > 0 else 0
    )
    new_labels = assign_to_nearest_cluster(
        index,
        existing_labels,
        new_embeddings,
        distance_threshold=threshold,
        next_cluster_id=max_existing_label,
    )

    # Append to index
    index.add(new_embeddings)  # type: ignore[call-arg]

    # Merge manifests
    updated_refs = [*manifest.faces, *new_refs]
    all_labels = np.concatenate([existing_labels, new_labels])

    # Build cluster UUID map
    existing_label_to_uuid: dict[int, str] = {}
    if existing_clusters_result:
        for cluster in existing_clusters_result.clusters:
            if cluster.face_indices:
                label = all_labels[cluster.face_indices[0]]
                existing_label_to_uuid[int(label)] = cluster.id

    cluster_map = _assign_cluster_uuids(all_labels, existing_label_to_uuid)
    _notify(on_stage_end, STAGE_CLUSTER)

    # ── Stage 4: save ──
    _notify(on_stage_start, STAGE_SAVE)
    updated_manifest = FaceManifest(faces=updated_refs)
    clusters = [
        FaceCluster(
            id=uuid_str,
            face_indices=sorted(int(idx) for idx in np.where(all_labels == label)[0]),
        )
        for label, uuid_str in sorted(cluster_map.items())
    ]
    result = FaceClusteringResult(
        threshold=threshold,
        face_count=len(all_labels),
        cluster_count=len(clusters),
        clusters=clusters,
    )

    all_sources = [*changes.new_sources, *changes.unchanged_sources]
    save_faiss_index(index, faiss_index_path(gallery_dir))
    save_manifest(gallery_dir, updated_manifest)
    save_clusters(gallery_dir, result)
    save_checksums(gallery_dir, _build_checksums(all_sources))
    _notify(on_stage_end, STAGE_SAVE)

    return GalleryFaceRefreshResult(
        total_faces=len(all_labels),
        total_clusters=len(clusters),
        new_faces=len(new_embeddings),
        mode="incremental",
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback:
        callback(stage)


def _compute_changes(
    album_dirs: list[Path],
    album_index: AlbumIndex,
    existing_checksums: AlbumFaceChecksums,
) -> _ChangeSet:
    """Compute which album face sources are new, modified, removed, or unchanged."""
    new: list[_AlbumFaceSource] = []
    modified: list[_AlbumFaceSource] = []
    unchanged: list[_AlbumFaceSource] = []
    seen_keys: set[tuple[str, str]] = set()

    for album_dir in album_dirs:
        metadata = load_album_metadata(album_dir)
        if metadata is None:
            continue
        album_id = metadata.id

        # Find all .npz files for this album
        faces_dir = album_dir / PHOTREE_DIR / FACES_DIR
        if not faces_dir.is_dir():
            continue

        for npz_file in sorted(faces_dir.glob("*.npz")):
            ms_name = npz_file.stem
            checksum = compute_npz_checksum(npz_file)
            src = _AlbumFaceSource(
                album_id=album_id,
                media_source=ms_name,
                npz_path=npz_file,
                checksum=checksum,
            )
            seen_keys.add((album_id, ms_name))

            old_checksum = existing_checksums.albums.get(album_id, {}).get(ms_name)
            if old_checksum is None:
                new.append(src)
            elif old_checksum != checksum:
                modified.append(src)
            else:
                unchanged.append(src)

    # Find removed
    removed: list[tuple[str, str]] = [
        (album_id, ms_name)
        for album_id, sources in existing_checksums.albums.items()
        for ms_name in sources
        if (album_id, ms_name) not in seen_keys
    ]

    return _ChangeSet(
        new_sources=new,
        modified_sources=modified,
        removed_album_sources=removed,
        unchanged_sources=unchanged,
    )


def _count_faces(npz_path: Path) -> int:
    """Count the number of faces in a .npz file."""
    data = np.load(npz_path, allow_pickle=True)
    return len(data["keys"]) if "keys" in data else 0


def _labels_from_clusters(
    result: FaceClusteringResult, manifest: FaceManifest
) -> np.ndarray:
    """Reconstruct per-face labels from cluster assignments."""
    labels = np.full(len(manifest.faces), -1, dtype=np.int32)
    for i, cluster in enumerate(result.clusters):
        for idx in cluster.face_indices:
            if 0 <= idx < len(labels):
                labels[idx] = i
    return labels


def _cluster_label_for(cluster: FaceCluster, labels: np.ndarray) -> int | None:
    """Return the label assigned to the faces in a cluster."""
    if cluster.face_indices:
        idx = cluster.face_indices[0]
        if 0 <= idx < len(labels):
            return int(labels[idx])
    return None


def _assign_cluster_uuids(
    labels: np.ndarray,
    existing_map: dict[int, str],
) -> dict[int, str]:
    """Assign UUIDs to cluster labels, reusing existing UUIDs where matched."""
    unique_labels = sorted(set(int(label) for label in labels))
    return {label: existing_map.get(label, str(uuid7())) for label in unique_labels}


def _build_checksums(sources: list[_AlbumFaceSource]) -> AlbumFaceChecksums:
    """Build checksums from a list of face sources."""
    albums: dict[str, dict[str, str]] = {}
    for src in sources:
        albums.setdefault(src.album_id, {})[src.media_source] = src.checksum
    return AlbumFaceChecksums(albums=albums)


def _save_empty(
    gallery_dir: Path,
    sources: list[_AlbumFaceSource],
    threshold: float,
) -> None:
    """Save empty clustering results."""
    save_manifest(gallery_dir, FaceManifest())
    save_clusters(
        gallery_dir,
        FaceClusteringResult(threshold=threshold),
    )
    save_checksums(gallery_dir, _build_checksums(sources))
