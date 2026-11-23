"""Gallery-level face clustering refresh — scan, index, cluster, save."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid7

import numpy as np

from photree.album.faces.protocol import EMBEDDING_DIM, FACES_DIR
from photree.album.faces.store import load_face_data, read_face_count
from photree.album.store.album_discovery import discover_albums
from photree.album.store.metadata import load_album_metadata
from photree.foundation.layout import ALBUMS_DIR, PHOTREE_DIR
from photree.gallery.faces.clustering import (
    add_to_index,
    assign_to_nearest_cluster,
    build_faiss_index,
    cluster_embeddings,
    load_faiss_index,
    match_clusters_by_medoid,
)
from photree.gallery.faces.manifest import (
    GalleryFaceState,
    compute_npz_checksum,
    faiss_index_path,
    load_checksums,
    load_clusters,
    load_manifest,
    save_checksums,
    save_face_state,
)
from photree.gallery.faces.protocol import (
    DEFAULT_CLUSTER_THRESHOLD,
    AlbumFaceChecksums,
    FaceCluster,
    FaceClusteringResult,
    FaceManifest,
    FaceReference,
)

if TYPE_CHECKING:
    import faiss

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
    """
    Result of a gallery face clustering refresh.

    Failures raise (e.g.
    :class:`~photree.foundation.metadata_io.InvalidMetadataError` for a corrupt
    ``clusters.yaml``) instead of being folded into the result: a
    refresh that cannot read its previous state must not save a new one.
    """

    total_faces: int = 0
    total_clusters: int = 0
    new_faces: int = 0
    mode: FaceRefreshMode = FaceRefreshMode.NONE


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
    removed_album_sources: tuple[tuple[str, str], ...]  # album ID, then media source
    unchanged_sources: tuple[_AlbumFaceSource, ...]

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_sources or self.modified_sources or self.removed_album_sources,
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
    """
    Refresh face clustering for the entire gallery.

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

    saved = _extendable_faces(run, changes, existing, force_full=force_full)
    if dry_run:
        run.skip(*_POST_SCAN_STAGES)
        return GalleryFaceRefreshResult(
            new_faces=sum(read_face_count(s.npz_path) for s in changes.new_sources),
            mode=FaceRefreshMode.FULL if saved is None else FaceRefreshMode.INCREMENTAL,
        )
    match saved:
        case None:
            return _run_full_cluster(run, changes, existing)
        case _:
            return _run_incremental(run, changes, saved)


@dataclass(frozen=True)
class _SavedFaces:
    """The clustered faces a previous refresh saved, which new faces extend."""

    index: faiss.IndexFlatIP
    manifest: FaceManifest
    clusters: FaceClusteringResult


def _extendable_faces(
    run: _Run,
    changes: _ChangeSet,
    existing: FaceClusteringResult | None,
    *,
    force_full: bool,
) -> _SavedFaces | None:
    """
    Return the saved faces when new faces can be added to them, else ``None`` (full).

    Missing clusters, index or manifest cannot be extended, so they force a
    full re-cluster too.
    """
    if existing is None or _needs_full_recluster(
        changes,
        existing,
        force_full=force_full,
        threshold=run.threshold,
    ):
        return None
    index = load_faiss_index(faiss_index_path(run.gallery_dir))
    manifest = load_manifest(run.gallery_dir)
    return (
        _SavedFaces(index, manifest, existing)
        if index is not None
        and manifest is not None
        and _is_extendable(index, manifest, existing, changes.new_sources)
        else None
    )


def _is_extendable(
    index: faiss.IndexFlatIP,
    manifest: FaceManifest,
    clusters: FaceClusteringResult,
    new_sources: tuple[_AlbumFaceSource, ...],
) -> bool:
    """
    Whether the saved files describe the same faces, none from *new_sources*.

    A save interrupted part-way leaves them disagreeing on the face count, or
    leaves faces in the manifest whose source the checksums do not record yet:
    extending that state would add those faces a second time.
    """
    ingested = {(face.album_id, face.media_source) for face in manifest.faces}
    return index.ntotal == len(manifest.faces) == clusters.face_count and not any(
        (src.album_id, src.media_source) in ingested for src in new_sources
    )


def _is_stale_empty(changes: _ChangeSet, existing: FaceClusteringResult | None) -> bool:
    """
    Clusters are empty although album face data exists.

    Handles a previous run that saved checksums before the ``.npz`` files
    were populated: nothing looks changed, yet nothing was ever clustered.
    """
    return bool(changes.unchanged_sources) and (
        existing is None or existing.face_count == 0
    )


def _needs_full_recluster(
    changes: _ChangeSet,
    existing: FaceClusteringResult,
    *,
    force_full: bool,
    threshold: float,
) -> bool:
    # With no clustered face yet, there is nothing to extend: assigning new faces
    # to an empty index would give each its own cluster instead of grouping them.
    return (
        force_full
        or bool(changes.modified_sources or changes.removed_album_sources)
        or existing.face_count == 0
        or existing.threshold != threshold
    )


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
        labels,
        _assign_cluster_uuids(labels, old_uuid_map, run.new_id),
    )
    run.end(STAGE_CLUSTER)

    _save_stage(run, index, FaceManifest(faces=all_refs), clusters, all_sources)
    return GalleryFaceRefreshResult(
        total_faces=len(embeddings),
        total_clusters=len(clusters),
        new_faces=sum(read_face_count(s.npz_path) for s in changes.new_sources),
        mode=FaceRefreshMode.FULL,
    )


def _run_incremental(
    run: _Run,
    changes: _ChangeSet,
    saved: _SavedFaces,
) -> GalleryFaceRefreshResult:
    """Add new faces to the existing index and assign to nearest cluster."""
    run.start(STAGE_BUILD_INDEX)
    new_refs, new_embeddings_list = _collect_all_faces(changes.new_sources)
    ingested_sources = (*changes.new_sources, *changes.unchanged_sources)
    if not new_embeddings_list:
        run.end(STAGE_BUILD_INDEX)
        run.skip(STAGE_CLUSTER)
        _save_checksums_stage(run, ingested_sources)
        return GalleryFaceRefreshResult(
            total_faces=saved.index.ntotal,
            total_clusters=saved.clusters.cluster_count,
            mode=FaceRefreshMode.INCREMENTAL,
        )
    new_embeddings = np.concatenate(new_embeddings_list, axis=0).astype(np.float32)
    existing_labels = _labels_from_clusters(saved.clusters, saved.manifest)
    run.end(STAGE_BUILD_INDEX)

    run.start(STAGE_CLUSTER)
    all_labels = _assign_new_faces(run, saved.index, existing_labels, new_embeddings)
    old_uuids = _extract_existing_label_uuids(saved.clusters, all_labels)
    clusters = _build_cluster_list(
        all_labels,
        _assign_cluster_uuids(all_labels, old_uuids, run.new_id),
    )
    run.end(STAGE_CLUSTER)

    _save_stage(
        run,
        saved.index,
        FaceManifest(faces=[*saved.manifest.faces, *new_refs]),
        clusters,
        ingested_sources,
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
    add_to_index(index, new_embeddings)
    return np.concatenate([existing_labels, new_labels])


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
    # An index whose rows no longer line up with the manifest (left by an older
    # photree, or by an interrupted save) cannot say which face each row is.
    if (
        not old_manifest
        or not old_index
        or old_index.ntotal == 0
        or old_index.ntotal != len(old_manifest.faces)
    ):
        return {}

    old_embeddings = np.zeros((old_index.ntotal, old_index.d), dtype=np.float32)
    # faiss's stubs overload reconstruct_n for torch.Tensor, which photree does not
    # install, so pyright reads the method's type as partially Unknown.
    old_index.reconstruct_n(0, old_index.ntotal, old_embeddings)  # pyright: ignore[reportUnknownMemberType]
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
    clusters_result: FaceClusteringResult,
    all_labels: np.ndarray,
) -> dict[int, str]:
    """Build a label→UUID map from existing cluster assignments."""
    return {
        int(all_labels[cluster.face_indices[0]]): cluster.id
        for cluster in clusters_result.clusters
        if cluster.face_indices
    }


def _labels_from_clusters(
    result: FaceClusteringResult,
    manifest: FaceManifest,
) -> np.ndarray:
    """
    Reconstruct per-face labels from cluster assignments.

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
    labels: np.ndarray,
    cluster_map: dict[int, str],
) -> list[FaceCluster]:
    """Build the list of :class:`FaceCluster` from labels and UUID assignments."""
    return [
        FaceCluster(
            id=uuid_str,
            face_indices=sorted(int(idx) for idx in np.where(labels == label)[0]),
        )
        for label, uuid_str in sorted(cluster_map.items())
    ]


def _save_stage(
    run: _Run,
    index: faiss.IndexFlatIP,
    manifest: FaceManifest,
    clusters: list[FaceCluster],
    sources: tuple[_AlbumFaceSource, ...],
) -> None:
    """Stage 4: save FAISS index, manifest, clusters, and checksums."""
    run.start(STAGE_SAVE)
    save_face_state(
        run.gallery_dir,
        GalleryFaceState(
            index=index,
            manifest=manifest,
            clusters=FaceClusteringResult(
                threshold=run.threshold,
                face_count=len(manifest.faces),
                cluster_count=len(clusters),
                clusters=clusters,
            ),
            checksums=_build_checksums(sources),
        ),
    )
    run.end(STAGE_SAVE)


def _save_checksums_stage(run: _Run, sources: tuple[_AlbumFaceSource, ...]) -> None:
    """
    Stage 4 when the new sources hold no faces: record their checksums only.

    The index, manifest and clusters are unchanged, but the checksums are what
    mark a source ingested: left out, every refresh would see it as new again.
    """
    run.start(STAGE_SAVE)
    save_checksums(run.gallery_dir, _build_checksums(sources))
    run.end(STAGE_SAVE)


def _save_empty(run: _Run, sources: tuple[_AlbumFaceSource, ...]) -> None:
    save_face_state(
        run.gallery_dir,
        GalleryFaceState(
            index=build_faiss_index(np.empty((0, EMBEDDING_DIM), dtype=np.float32)),
            manifest=FaceManifest(),
            clusters=FaceClusteringResult(threshold=run.threshold),
            checksums=_build_checksums(sources),
        ),
    )


def _build_checksums(sources: tuple[_AlbumFaceSource, ...]) -> AlbumFaceChecksums:
    by_album = attrgetter("album_id")
    return AlbumFaceChecksums(
        albums={
            album_id: {src.media_source: src.checksum for src in album_sources}
            for album_id, album_sources in groupby(
                sorted(sources, key=by_album),
                key=by_album,
            )
        },
    )
