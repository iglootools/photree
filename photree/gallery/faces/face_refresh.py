"""Gallery-level face clustering refresh — scan, index, cluster, save."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    import faiss  # type: ignore[import-untyped]

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

_POST_SCAN_STAGES = (STAGE_BUILD_INDEX, STAGE_CLUSTER, STAGE_SAVE)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class FaceRefreshMode(StrEnum):
    """How a refresh updated the gallery clusters."""

    NONE = "none"
    """Nothing changed since the last run."""

    INCREMENTAL = "incremental"
    """New faces were assigned to their nearest existing cluster."""

    FULL = "full"
    """Everything was re-clustered (UUIDs recovered by medoid matching)."""


@dataclass(frozen=True)
class GalleryFaceRefreshResult:
    """Result of a gallery face clustering refresh.

    Failures raise (e.g. :class:`~photree.fsprotocol.InvalidMetadataError` for
    a corrupt ``clusters.yaml``) instead of being folded into the result: a
    refresh that cannot read its previous state must not save a new one.
    """

    total_faces: int = 0
    total_clusters: int = 0
    new_faces: int = 0
    removed_faces: int = 0
    mode: FaceRefreshMode = FaceRefreshMode.NONE


# ---------------------------------------------------------------------------
# Internal data types
# ---------------------------------------------------------------------------


class _SourceStatus(StrEnum):
    NEW = "new"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class _AlbumFaceSource:
    album_id: str
    album_dir: Path
    media_source: str
    npz_path: Path
    checksum: str


@dataclass(frozen=True)
class _ChangeSet:
    new_sources: tuple[_AlbumFaceSource, ...]
    modified_sources: tuple[_AlbumFaceSource, ...]
    removed_album_sources: tuple[tuple[str, str], ...]  # (album_id, media_source)
    unchanged_sources: tuple[_AlbumFaceSource, ...]

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_sources or self.modified_sources or self.removed_album_sources
        )


def _new_cluster_id() -> str:
    return str(uuid7())


@dataclass(frozen=True)
class _Run:
    """Per-run context: where to save, how to cluster, whom to notify."""

    gallery_dir: Path
    threshold: float
    new_id: Callable[[], str]
    on_stage_start: Callable[[str], None] | None
    on_stage_end: Callable[[str], None] | None

    def start(self, stage: str) -> None:
        if self.on_stage_start is not None:
            self.on_stage_start(stage)

    def end(self, stage: str) -> None:
        if self.on_stage_end is not None:
            self.on_stage_end(stage)

    def skip(self, *stages: str) -> None:
        """Notify start/end for *stages* without doing work."""
        for stage in stages:
            self.start(stage)
            self.end(stage)


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
    new_id: Callable[[], str] = _new_cluster_id,
) -> GalleryFaceRefreshResult:
    """Refresh face clustering for the entire gallery.

    *distance_threshold* ``None`` means the default; ``0.0`` is a valid
    (strictest) threshold, not a missing one.
    """
    threshold = (
        DEFAULT_CLUSTER_THRESHOLD if distance_threshold is None else distance_threshold
    )
    run = _Run(gallery_dir, threshold, new_id, on_stage_start, on_stage_end)
    run.start(STAGE_SCAN_FACE_DATA)
    changes = _scan_face_data(gallery_dir)
    run.end(STAGE_SCAN_FACE_DATA)

    # Loaded once and threaded through: every later step needs the same view.
    existing = load_clusters(gallery_dir)
    if not (changes.has_changes or force_full or _is_stale_empty(changes, existing)):
        run.skip(*_POST_SCAN_STAGES)
        return GalleryFaceRefreshResult(
            total_faces=existing.face_count if existing else 0,
            total_clusters=existing.cluster_count if existing else 0,
            mode=FaceRefreshMode.NONE,
        )

    index = _extendable_index(run, changes, existing, force_full=force_full)
    if dry_run:
        run.skip(*_POST_SCAN_STAGES)
        return GalleryFaceRefreshResult(
            new_faces=sum(_count_faces(s.npz_path) for s in changes.new_sources),
            mode=FaceRefreshMode.FULL if index is None else FaceRefreshMode.INCREMENTAL,
        )
    match index:
        case None:
            return _run_full_cluster(run, changes, existing)
        case _:
            return _run_incremental(run, changes, existing, index)


def _extendable_index(
    run: _Run,
    changes: _ChangeSet,
    existing: FaceClusteringResult | None,
    *,
    force_full: bool,
) -> faiss.IndexFlatIP | None:
    """The saved index when new faces can be added to it, else ``None`` (full).

    A missing index cannot be extended, so it forces a full re-cluster too.
    """
    needs_full = _needs_full_recluster(
        changes, existing, force_full=force_full, threshold=run.threshold
    )
    return None if needs_full else load_faiss_index(faiss_index_path(run.gallery_dir))


def _is_stale_empty(changes: _ChangeSet, existing: FaceClusteringResult | None) -> bool:
    """Clusters are empty although album face data exists.

    Handles a previous run that saved checksums before the ``.npz`` files
    were populated: nothing looks changed, yet nothing was ever clustered.
    """
    return bool(changes.unchanged_sources) and (
        existing is None or existing.face_count == 0
    )


def _needs_full_recluster(
    changes: _ChangeSet,
    existing: FaceClusteringResult | None,
    *,
    force_full: bool,
    threshold: float,
) -> bool:
    """Determine whether a full re-cluster is needed."""
    return (
        force_full
        or bool(changes.modified_sources or changes.removed_album_sources)
        or _is_stale_empty(changes, existing)
        or (existing is not None and existing.threshold != threshold)
    )


# ---------------------------------------------------------------------------
# Full re-cluster
# ---------------------------------------------------------------------------


def _run_full_cluster(
    run: _Run,
    changes: _ChangeSet,
    existing: FaceClusteringResult | None,
) -> GalleryFaceRefreshResult:
    """Rebuild the FAISS index and re-cluster everything."""
    all_sources = (
        *changes.new_sources,
        *changes.modified_sources,
        *changes.unchanged_sources,
    )

    run.start(STAGE_BUILD_INDEX)
    all_refs, all_embeddings = _collect_all_faces(all_sources)
    if not all_embeddings:
        run.end(STAGE_BUILD_INDEX)
        run.skip(STAGE_CLUSTER, STAGE_SAVE)
        _save_empty(run, all_sources)
        return GalleryFaceRefreshResult(mode=FaceRefreshMode.FULL)
    embeddings = np.concatenate(all_embeddings, axis=0).astype(np.float32)
    index = build_faiss_index(embeddings)
    run.end(STAGE_BUILD_INDEX)

    run.start(STAGE_CLUSTER)
    labels = cluster_embeddings(embeddings, distance_threshold=run.threshold)
    old_uuid_map = _recover_old_uuid_map(run, existing, embeddings, labels)
    clusters = _build_cluster_list(
        labels, _assign_cluster_uuids(labels, old_uuid_map, run.new_id)
    )
    run.end(STAGE_CLUSTER)

    _save_stage(run, index, FaceManifest(faces=all_refs), clusters, all_sources)
    return GalleryFaceRefreshResult(
        total_faces=len(embeddings),
        total_clusters=len(clusters),
        new_faces=sum(_count_faces(s.npz_path) for s in changes.new_sources),
        mode=FaceRefreshMode.FULL,
    )


# ---------------------------------------------------------------------------
# Incremental assignment
# ---------------------------------------------------------------------------


def _run_incremental(
    run: _Run,
    changes: _ChangeSet,
    existing: FaceClusteringResult | None,
    index: faiss.IndexFlatIP,
) -> GalleryFaceRefreshResult:
    """Add new faces to the existing index and assign to nearest cluster."""
    run.start(STAGE_BUILD_INDEX)
    manifest = load_manifest(run.gallery_dir) or FaceManifest()
    new_refs, new_embeddings_list = _collect_all_faces(changes.new_sources)
    if not new_embeddings_list:
        run.end(STAGE_BUILD_INDEX)
        run.skip(STAGE_CLUSTER, STAGE_SAVE)
        return GalleryFaceRefreshResult(
            total_faces=index.ntotal,
            total_clusters=existing.cluster_count if existing else 0,
            mode=FaceRefreshMode.INCREMENTAL,
        )
    new_embeddings = np.concatenate(new_embeddings_list, axis=0).astype(np.float32)
    existing_labels = (
        _labels_from_clusters(existing, manifest)
        if existing
        else np.array([], dtype=np.int32)
    )
    run.end(STAGE_BUILD_INDEX)

    run.start(STAGE_CLUSTER)
    all_labels = _assign_new_faces(run, index, existing_labels, new_embeddings)
    old_uuids = _extract_existing_label_uuids(existing, all_labels)
    clusters = _build_cluster_list(
        all_labels, _assign_cluster_uuids(all_labels, old_uuids, run.new_id)
    )
    run.end(STAGE_CLUSTER)

    _save_stage(
        run,
        index,
        FaceManifest(faces=[*manifest.faces, *new_refs]),
        clusters,
        (*changes.new_sources, *changes.unchanged_sources),
    )
    return GalleryFaceRefreshResult(
        total_faces=len(all_labels),
        total_clusters=len(clusters),
        new_faces=len(new_embeddings),
        mode=FaceRefreshMode.INCREMENTAL,
    )


def _assign_new_faces(
    run: _Run,
    index: faiss.IndexFlatIP,
    existing_labels: np.ndarray,
    new_embeddings: np.ndarray,
) -> np.ndarray:
    """Label the new faces, append them to *index*, and return all labels."""
    next_label = int(existing_labels.max()) + 1 if len(existing_labels) > 0 else 0
    new_labels = assign_to_nearest_cluster(
        index,
        existing_labels,
        new_embeddings,
        distance_threshold=run.threshold,
        next_cluster_id=next_label,
    )
    index.add(new_embeddings)  # type: ignore[call-arg]
    return np.concatenate([existing_labels, new_labels])


# ---------------------------------------------------------------------------
# Scanning and change detection
# ---------------------------------------------------------------------------


def _scan_face_data(gallery_dir: Path) -> _ChangeSet:
    """Scan all albums and compute which face sources changed."""
    album_dirs = discover_albums(gallery_dir / ALBUMS_DIR)
    existing_checksums = load_checksums(gallery_dir) or AlbumFaceChecksums()
    return _compute_changes(album_dirs, existing_checksums)


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

    def with_status(status: _SourceStatus) -> tuple[_AlbumFaceSource, ...]:
        return tuple(src for src, s in classified if s is status)

    return _ChangeSet(
        new_sources=with_status(_SourceStatus.NEW),
        modified_sources=with_status(_SourceStatus.MODIFIED),
        removed_album_sources=tuple(
            (album_id, ms_name)
            for album_id, sources in existing_checksums.albums.items()
            for ms_name in sources
            if (album_id, ms_name) not in seen_keys
        ),
        unchanged_sources=with_status(_SourceStatus.UNCHANGED),
    )


def _scan_album_face_sources(album_dir: Path) -> list[_AlbumFaceSource]:
    """Discover all face .npz files for an album."""
    metadata = load_album_metadata(album_dir)
    faces_dir = album_dir / PHOTREE_DIR / FACES_DIR
    if metadata is None or not faces_dir.is_dir():
        return []
    return [
        _AlbumFaceSource(
            album_id=metadata.id,
            album_dir=album_dir,
            media_source=npz_file.stem,
            npz_path=npz_file,
            checksum=compute_npz_checksum(npz_file),
        )
        for npz_file in sorted(faces_dir.glob("*.npz"))
    ]


def _classify_source(
    src: _AlbumFaceSource,
    existing_checksums: AlbumFaceChecksums,
) -> _SourceStatus:
    """Classify a face source as new, modified, or unchanged."""
    old_checksum = existing_checksums.albums.get(src.album_id, {}).get(src.media_source)
    match old_checksum:
        case None:
            return _SourceStatus.NEW
        case ck if ck != src.checksum:
            return _SourceStatus.MODIFIED
        case _:
            return _SourceStatus.UNCHANGED


# ---------------------------------------------------------------------------
# Face data loading
# ---------------------------------------------------------------------------


def _collect_all_faces(
    sources: tuple[_AlbumFaceSource, ...],
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
    data = load_face_data(src.album_dir, src.media_source)
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
    run: _Run,
    existing: FaceClusteringResult | None,
    new_embeddings: np.ndarray,
    new_labels: np.ndarray,
) -> dict[int, str]:
    """Recover old cluster UUIDs via medoid matching after a full re-cluster."""
    if existing is None:
        return {}
    old_manifest = load_manifest(run.gallery_dir)
    old_index = load_faiss_index(faiss_index_path(run.gallery_dir))
    if not old_manifest or not old_index or old_index.ntotal == 0:
        return {}

    old_embeddings = np.zeros((old_index.ntotal, old_index.d), dtype=np.float32)
    old_index.reconstruct_n(0, old_index.ntotal, old_embeddings)
    old_labels = _labels_from_clusters(existing, old_manifest)
    old_id_map = {
        label: c.id
        for c in existing.clusters
        for label in [_cluster_label_for(c, old_labels)]
        if label is not None
    }
    return match_clusters_by_medoid(
        old_embeddings,
        old_labels,
        old_id_map,
        new_embeddings,
        new_labels,
        threshold=run.threshold,
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
    new_id: Callable[[], str],
) -> dict[int, str]:
    """Assign UUIDs to cluster labels, reusing existing UUIDs where matched."""
    unique_labels = sorted({int(label) for label in labels})
    return {
        label: existing_map[label] if label in existing_map else new_id()
        for label in unique_labels
    }


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


def _save_stage(
    run: _Run,
    index: faiss.IndexFlatIP,
    manifest: FaceManifest,
    clusters: list[FaceCluster],
    sources: tuple[_AlbumFaceSource, ...],
) -> None:
    """Stage 4: save FAISS index, manifest, clusters, and checksums."""
    run.start(STAGE_SAVE)
    result = FaceClusteringResult(
        threshold=run.threshold,
        face_count=len(manifest.faces),
        cluster_count=len(clusters),
        clusters=clusters,
    )
    save_faiss_index(index, faiss_index_path(run.gallery_dir))
    save_manifest(run.gallery_dir, manifest)
    save_clusters(run.gallery_dir, result)
    save_checksums(run.gallery_dir, _build_checksums(sources))
    run.end(STAGE_SAVE)


def _save_empty(run: _Run, sources: tuple[_AlbumFaceSource, ...]) -> None:
    """Save empty clustering results."""
    save_manifest(run.gallery_dir, FaceManifest())
    save_clusters(run.gallery_dir, FaceClusteringResult(threshold=run.threshold))
    save_checksums(run.gallery_dir, _build_checksums(sources))


def _build_checksums(sources: tuple[_AlbumFaceSource, ...]) -> AlbumFaceChecksums:
    """Build checksums from a list of face sources."""
    return AlbumFaceChecksums(
        albums={
            album_id: {
                src.media_source: src.checksum
                for src in sources
                if src.album_id == album_id
            }
            for album_id in dict.fromkeys(src.album_id for src in sources)
        }
    )


def _count_faces(npz_path: Path) -> int:
    """Count the number of faces in a .npz file."""
    # ``keys`` is saved as an object array (see album/faces/store.py), which
    # numpy only reads back with pickling enabled; the file is our own cache.
    with np.load(npz_path, allow_pickle=True) as data:
        return len(data["keys"]) if "keys" in data else 0
