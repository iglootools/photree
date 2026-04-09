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
# Internal data types
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
    """Refresh face clustering for the entire gallery."""
    threshold = distance_threshold or DEFAULT_CLUSTER_THRESHOLD

    # ── Stage 1: scan-face-data ──
    _notify(on_stage_start, STAGE_SCAN_FACE_DATA)
    changes = _scan_face_data(gallery_dir)
    _notify(on_stage_end, STAGE_SCAN_FACE_DATA)

    has_changes = (
        changes.new_sources or changes.modified_sources or changes.removed_album_sources
    )
    if not has_changes and not force_full:
        _skip_remaining_stages(on_stage_start, on_stage_end)
        existing_clusters = load_clusters(gallery_dir)
        return GalleryFaceRefreshResult(
            total_faces=existing_clusters.face_count if existing_clusters else 0,
            total_clusters=existing_clusters.cluster_count if existing_clusters else 0,
            mode="none",
        )

    needs_full = _needs_full_recluster(changes, force_full, gallery_dir, threshold)

    if dry_run:
        _skip_remaining_stages(on_stage_start, on_stage_end)
        return GalleryFaceRefreshResult(
            new_faces=sum(_count_faces(s.npz_path) for s in changes.new_sources),
            mode="full" if needs_full else "incremental",
        )

    if needs_full:
        return _run_full_cluster(
            gallery_dir,
            changes,
            threshold=threshold,
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
    *,
    threshold: float,
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
) -> GalleryFaceRefreshResult:
    """Rebuild the FAISS index and re-cluster everything."""
    all_sources = [
        *changes.new_sources,
        *changes.modified_sources,
        *changes.unchanged_sources,
    ]

    # ── Stage 2: build-index ──
    _notify(on_stage_start, STAGE_BUILD_INDEX)
    all_refs, all_embeddings = _collect_all_faces(all_sources)

    if not all_embeddings:
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        _skip_stages(on_stage_start, on_stage_end, STAGE_CLUSTER, STAGE_SAVE)
        _save_empty(gallery_dir, all_sources, threshold)
        return GalleryFaceRefreshResult(mode="full")

    embeddings = np.concatenate(all_embeddings, axis=0).astype(np.float32)
    index = build_faiss_index(embeddings)
    _notify(on_stage_end, STAGE_BUILD_INDEX)

    # ── Stage 3: cluster ──
    _notify(on_stage_start, STAGE_CLUSTER)
    labels = cluster_embeddings(embeddings, distance_threshold=threshold)
    old_uuid_map = _recover_old_uuid_map(gallery_dir, embeddings, labels, threshold)
    cluster_map = _assign_cluster_uuids(labels, old_uuid_map)
    _notify(on_stage_end, STAGE_CLUSTER)

    # ── Stage 4: save ──
    _notify(on_stage_start, STAGE_SAVE)
    clusters = _build_cluster_list(labels, cluster_map)
    _save_results(
        gallery_dir,
        index=index,
        manifest=FaceManifest(faces=all_refs),
        clusters=clusters,
        threshold=threshold,
        sources=all_sources,
    )
    _notify(on_stage_end, STAGE_SAVE)

    return GalleryFaceRefreshResult(
        total_faces=len(embeddings),
        total_clusters=len(clusters),
        new_faces=sum(_count_faces(s.npz_path) for s in changes.new_sources),
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
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        return _run_full_cluster(
            gallery_dir,
            changes,
            threshold=threshold,
            on_stage_start=lambda _: None,
            on_stage_end=lambda _: None,
        )

    new_refs, new_embeddings_list = _collect_all_faces(changes.new_sources)

    if not new_embeddings_list:
        _notify(on_stage_end, STAGE_BUILD_INDEX)
        _skip_stages(on_stage_start, on_stage_end, STAGE_CLUSTER, STAGE_SAVE)
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

    index.add(new_embeddings)  # type: ignore[call-arg]
    all_labels = np.concatenate([existing_labels, new_labels])

    existing_label_to_uuid = _extract_existing_label_uuids(
        existing_clusters_result, all_labels
    )
    cluster_map = _assign_cluster_uuids(all_labels, existing_label_to_uuid)
    _notify(on_stage_end, STAGE_CLUSTER)

    # ── Stage 4: save ──
    _notify(on_stage_start, STAGE_SAVE)
    clusters = _build_cluster_list(all_labels, cluster_map)
    all_sources = [*changes.new_sources, *changes.unchanged_sources]
    _save_results(
        gallery_dir,
        index=index,
        manifest=FaceManifest(faces=[*manifest.faces, *new_refs]),
        clusters=clusters,
        threshold=threshold,
        sources=all_sources,
    )
    _notify(on_stage_end, STAGE_SAVE)

    return GalleryFaceRefreshResult(
        total_faces=len(all_labels),
        total_clusters=len(clusters),
        new_faces=len(new_embeddings),
        mode="incremental",
    )


# ---------------------------------------------------------------------------
# Scanning and change detection
# ---------------------------------------------------------------------------


def _scan_face_data(gallery_dir: Path) -> _ChangeSet:
    """Scan all albums and compute which face sources changed."""
    albums_dir = gallery_dir / ALBUMS_DIR
    album_dirs = discover_albums(albums_dir)
    existing_checksums = load_checksums(gallery_dir) or AlbumFaceChecksums()
    return _compute_changes(album_dirs, existing_checksums)


def _needs_full_recluster(
    changes: _ChangeSet,
    force_full: bool,
    gallery_dir: Path,
    threshold: float,
) -> bool:
    """Determine whether a full re-cluster is needed."""
    if force_full or changes.modified_sources or changes.removed_album_sources:
        return True
    existing_clusters = load_clusters(gallery_dir)
    return existing_clusters is not None and existing_clusters.threshold != threshold


def _compute_changes(
    album_dirs: list[Path],
    existing_checksums: AlbumFaceChecksums,
) -> _ChangeSet:
    """Compute which album face sources are new, modified, removed, or unchanged."""
    all_sources = [
        src for album_dir in album_dirs for src in _scan_album_face_sources(album_dir)
    ]

    classified = [
        (src, _classify_source(src, existing_checksums)) for src in all_sources
    ]

    seen_keys = {(src.album_id, src.media_source) for src in all_sources}

    return _ChangeSet(
        new_sources=[src for src, cat in classified if cat == "new"],
        modified_sources=[src for src, cat in classified if cat == "modified"],
        removed_album_sources=[
            (album_id, ms_name)
            for album_id, sources in existing_checksums.albums.items()
            for ms_name in sources
            if (album_id, ms_name) not in seen_keys
        ],
        unchanged_sources=[src for src, cat in classified if cat == "unchanged"],
    )


def _scan_album_face_sources(album_dir: Path) -> list[_AlbumFaceSource]:
    """Discover all face .npz files for an album."""
    metadata = load_album_metadata(album_dir)
    if metadata is None:
        return []
    faces_dir = album_dir / PHOTREE_DIR / FACES_DIR
    if not faces_dir.is_dir():
        return []
    return [
        _AlbumFaceSource(
            album_id=metadata.id,
            media_source=npz_file.stem,
            npz_path=npz_file,
            checksum=compute_npz_checksum(npz_file),
        )
        for npz_file in sorted(faces_dir.glob("*.npz"))
    ]


def _classify_source(
    src: _AlbumFaceSource,
    existing_checksums: AlbumFaceChecksums,
) -> str:
    """Classify a face source as 'new', 'modified', or 'unchanged'."""
    old_checksum = existing_checksums.albums.get(src.album_id, {}).get(src.media_source)
    match old_checksum:
        case None:
            return "new"
        case ck if ck != src.checksum:
            return "modified"
        case _:
            return "unchanged"


# ---------------------------------------------------------------------------
# Face data loading
# ---------------------------------------------------------------------------


def _collect_all_faces(
    sources: list[_AlbumFaceSource],
) -> tuple[list[FaceReference], list[np.ndarray]]:
    """Load and flatten face refs + embeddings from multiple sources."""
    loaded = [_load_source_faces(src) for src in sources]
    refs = [ref for source_refs, _ in loaded if source_refs for ref in source_refs]
    embeddings = [emb for _, emb in loaded if emb is not None]
    return (refs, embeddings)


def _load_source_faces(
    src: _AlbumFaceSource,
) -> tuple[list[FaceReference] | None, np.ndarray | None]:
    """Load face references and embeddings from a single album face source."""
    album_dir = src.npz_path.parent.parent.parent
    data = load_face_data(album_dir, src.media_source)
    if data is None or data.count == 0:
        return (None, None)
    refs = [
        FaceReference(
            album_id=src.album_id,
            media_source=src.media_source,
            media_key=str(data.keys[i]),
            face_index=int(data.face_indices[i]),
        )
        for i in range(data.count)
    ]
    return (refs, data.embeddings)


# ---------------------------------------------------------------------------
# Cluster label / UUID helpers
# ---------------------------------------------------------------------------


def _recover_old_uuid_map(
    gallery_dir: Path,
    new_embeddings: np.ndarray,
    new_labels: np.ndarray,
    threshold: float,
) -> dict[int, str]:
    """Recover old cluster UUIDs via medoid matching after a full re-cluster."""
    existing_clusters = load_clusters(gallery_dir)
    if existing_clusters is None:
        return {}

    old_manifest = load_manifest(gallery_dir)
    old_index = load_faiss_index(faiss_index_path(gallery_dir))
    if not old_manifest or not old_index or old_index.ntotal == 0:
        return {}

    old_embeddings = np.zeros((old_index.ntotal, old_index.d), dtype=np.float32)
    old_index.reconstruct_n(0, old_index.ntotal, old_embeddings)
    old_labels = _labels_from_clusters(existing_clusters, old_manifest)
    old_id_map = {
        label: c.id
        for c in existing_clusters.clusters
        for label in [_cluster_label_for(c, old_labels)]
        if label is not None
    }
    return match_clusters_by_medoid(
        old_embeddings,
        old_labels,
        old_id_map,
        new_embeddings,
        new_labels,
        threshold=threshold,
    )


def _extract_existing_label_uuids(
    clusters_result: FaceClusteringResult | None,
    all_labels: np.ndarray,
) -> dict[int, str]:
    """Build a label→UUID map from existing cluster assignments."""
    if clusters_result is None:
        return {}
    return {
        int(all_labels[cluster.face_indices[0]]): cluster.id
        for cluster in clusters_result.clusters
        if cluster.face_indices
    }


def _labels_from_clusters(
    result: FaceClusteringResult, manifest: FaceManifest
) -> np.ndarray:
    """Reconstruct per-face labels from cluster assignments.

    Numpy array mutation is inherent here — cannot be expressed as a
    single comprehension.
    """
    labels = np.full(len(manifest.faces), -1, dtype=np.int32)
    for i, cluster in enumerate(result.clusters):
        for idx in cluster.face_indices:
            if 0 <= idx < len(labels):
                labels[idx] = i
    return labels


def _cluster_label_for(cluster: FaceCluster, labels: np.ndarray) -> int | None:
    """Return the label assigned to the first face in a cluster."""
    if not cluster.face_indices:
        return None
    idx = cluster.face_indices[0]
    return int(labels[idx]) if 0 <= idx < len(labels) else None


def _assign_cluster_uuids(
    labels: np.ndarray,
    existing_map: dict[int, str],
) -> dict[int, str]:
    """Assign UUIDs to cluster labels, reusing existing UUIDs where matched."""
    unique_labels = sorted(set(int(label) for label in labels))
    return {label: existing_map.get(label, str(uuid7())) for label in unique_labels}


def _build_cluster_list(
    labels: np.ndarray, cluster_map: dict[int, str]
) -> list[FaceCluster]:
    """Build the list of :class:`FaceCluster` from labels and UUID assignments."""
    return [
        FaceCluster(
            id=uuid_str,
            face_indices=sorted(int(idx) for idx in np.where(labels == label)[0]),
        )
        for label, uuid_str in sorted(cluster_map.items())
    ]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _save_results(
    gallery_dir: Path,
    *,
    index: object,  # faiss.IndexFlatIP (untyped SWIG binding)
    manifest: FaceManifest,
    clusters: list[FaceCluster],
    threshold: float,
    sources: list[_AlbumFaceSource],
) -> None:
    """Save FAISS index, manifest, clusters, and checksums."""
    result = FaceClusteringResult(
        threshold=threshold,
        face_count=len(manifest.faces),
        cluster_count=len(clusters),
        clusters=clusters,
    )
    save_faiss_index(index, faiss_index_path(gallery_dir))  # type: ignore[arg-type]
    save_manifest(gallery_dir, manifest)
    save_clusters(gallery_dir, result)
    save_checksums(gallery_dir, _build_checksums(sources))


def _save_empty(
    gallery_dir: Path,
    sources: list[_AlbumFaceSource],
    threshold: float,
) -> None:
    """Save empty clustering results."""
    save_manifest(gallery_dir, FaceManifest())
    save_clusters(gallery_dir, FaceClusteringResult(threshold=threshold))
    save_checksums(gallery_dir, _build_checksums(sources))


def _build_checksums(sources: list[_AlbumFaceSource]) -> AlbumFaceChecksums:
    """Build checksums from a list of face sources."""
    albums: dict[str, dict[str, str]] = {}
    for src in sources:
        albums.setdefault(src.album_id, {})[src.media_source] = src.checksum
    return AlbumFaceChecksums(albums=albums)


# ---------------------------------------------------------------------------
# Stage notification helpers
# ---------------------------------------------------------------------------


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback:
        callback(stage)


def _skip_remaining_stages(
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
) -> None:
    """Notify start/end for stages 2–4 without doing work."""
    _skip_stages(
        on_stage_start, on_stage_end, STAGE_BUILD_INDEX, STAGE_CLUSTER, STAGE_SAVE
    )


def _skip_stages(
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
    *stages: str,
) -> None:
    for stage in stages:
        _notify(on_stage_start, stage)
        _notify(on_stage_end, stage)


def _count_faces(npz_path: Path) -> int:
    """Count the number of faces in a .npz file."""
    data = np.load(npz_path, allow_pickle=True)
    return len(data["keys"]) if "keys" in data else 0
