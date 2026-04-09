"""Face clustering — FAISS index management, agglomerative clustering, medoid matching."""

from __future__ import annotations

from pathlib import Path

import faiss  # type: ignore[import-untyped]
import numpy as np
from sklearn.cluster import AgglomerativeClustering  # type: ignore[import-untyped]

from .protocol import DEFAULT_CLUSTER_THRESHOLD


# ---------------------------------------------------------------------------
# FAISS index management
# ---------------------------------------------------------------------------


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """Build a FAISS inner-product index from L2-normalized embeddings.

    For normalized vectors, inner product = cosine similarity.
    """
    dim = embeddings.shape[1] if embeddings.ndim == 2 else 512
    index = faiss.IndexFlatIP(dim)  # type: ignore[call-arg]
    if len(embeddings) > 0:
        index.add(embeddings.astype(np.float32))  # type: ignore[call-arg]
    return index


def save_faiss_index(index: faiss.IndexFlatIP, path: Path) -> None:
    """Serialize a FAISS index to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))


def load_faiss_index(path: Path) -> faiss.IndexFlatIP | None:
    """Load a FAISS index from disk, or ``None`` if the file is missing."""
    if not path.is_file():
        return None
    return faiss.read_index(str(path))


# ---------------------------------------------------------------------------
# Agglomerative clustering
# ---------------------------------------------------------------------------


def cluster_embeddings(
    embeddings: np.ndarray,
    *,
    distance_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> np.ndarray:
    """Cluster face embeddings into identity groups.

    Returns an array of cluster labels (int32), one per face.
    Uses agglomerative clustering with cosine distance and average linkage.

    For large N (>10000), uses a sparse connectivity matrix from FAISS k-NN
    to avoid the O(N^2) memory cost of a full distance matrix.
    """
    n = len(embeddings)
    if n == 0:
        return np.array([], dtype=np.int32)
    if n == 1:
        return np.array([0], dtype=np.int32)

    connectivity = (
        _build_sparse_connectivity(embeddings, k=min(50, n - 1)) if n > 10_000 else None
    )

    clustering = AgglomerativeClustering(
        n_clusters=None,  # type: ignore[arg-type]  # sklearn expects int | None
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
        connectivity=connectivity,
    )
    labels = clustering.fit_predict(embeddings)
    return labels.astype(np.int32)


def _build_sparse_connectivity(embeddings: np.ndarray, *, k: int) -> object:
    """Build a sparse k-NN connectivity matrix using FAISS.

    Returns a binary adjacency matrix where entry (i, j) = 1 iff
    j is among the k nearest neighbors of i.
    """
    from scipy.sparse import lil_matrix

    index = faiss.IndexFlatIP(embeddings.shape[1])  # type: ignore[call-arg]
    index.add(embeddings.astype(np.float32))  # type: ignore[call-arg]
    _, indices = index.search(embeddings.astype(np.float32), k + 1)  # type: ignore[call-arg]

    n = len(embeddings)
    connectivity = lil_matrix((n, n), dtype=np.int8)
    for i in range(n):
        for j in indices[i]:
            if j != i and j >= 0:
                connectivity[i, j] = 1
                connectivity[j, i] = 1

    return connectivity.tocsr()


# ---------------------------------------------------------------------------
# Incremental assignment
# ---------------------------------------------------------------------------


def assign_to_nearest_cluster(
    index: faiss.IndexFlatIP,
    existing_labels: np.ndarray,
    new_embeddings: np.ndarray,
    *,
    distance_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
    next_cluster_id: int = 0,
) -> np.ndarray:
    """Assign new faces to existing clusters or create singleton clusters.

    For each new face, finds the nearest face in the existing index.
    If the cosine distance is within the threshold, assigns it to that
    face's cluster. Otherwise, creates a new cluster.

    Returns an array of cluster labels for the new faces.
    """
    if len(new_embeddings) == 0:
        return np.array([], dtype=np.int32)

    if index.ntotal == 0:
        # No existing faces — each new face gets its own cluster
        return np.arange(
            next_cluster_id, next_cluster_id + len(new_embeddings), dtype=np.int32
        )

    similarities, nn_indices = index.search(new_embeddings.astype(np.float32), 1)  # type: ignore[call-arg]

    new_labels = np.empty(len(new_embeddings), dtype=np.int32)
    current_id = next_cluster_id

    for i, (sim, nn_idx) in enumerate(zip(similarities[:, 0], nn_indices[:, 0])):
        cosine_distance = 1.0 - sim
        if cosine_distance <= distance_threshold and nn_idx >= 0:
            new_labels[i] = existing_labels[nn_idx]
        else:
            new_labels[i] = current_id
            current_id += 1

    return new_labels


# ---------------------------------------------------------------------------
# Medoid matching (cluster UUID stability across full re-clusters)
# ---------------------------------------------------------------------------


def compute_medoids(
    embeddings: np.ndarray,
    labels: np.ndarray,
) -> dict[int, int]:
    """Compute the medoid index for each cluster.

    The medoid is the face closest to the cluster centroid.
    Returns ``{cluster_label: face_index}``.
    """
    unique_labels = np.unique(labels)
    medoids: dict[int, int] = {}

    for label in unique_labels:
        mask = labels == label
        cluster_indices = np.where(mask)[0]
        cluster_embeddings = embeddings[mask]

        centroid = cluster_embeddings.mean(axis=0)
        centroid = centroid / (np.linalg.norm(centroid) + 1e-10)

        similarities = cluster_embeddings @ centroid
        best_idx = cluster_indices[np.argmax(similarities)]
        medoids[int(label)] = int(best_idx)

    return medoids


def match_clusters_by_medoid(
    old_embeddings: np.ndarray,
    old_labels: np.ndarray,
    old_cluster_ids: dict[int, str],
    new_embeddings: np.ndarray,
    new_labels: np.ndarray,
    *,
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[int, str]:
    """Match new cluster labels to old cluster UUIDs via medoid similarity.

    For each old cluster, computes its medoid embedding. For each new cluster,
    finds the old cluster whose medoid is most similar. If similarity exceeds
    the threshold, the new cluster inherits the old UUID.

    Returns ``{new_label: uuid_string}``.
    """
    if not old_cluster_ids or len(old_embeddings) == 0:
        return {}

    old_medoids = compute_medoids(old_embeddings, old_labels)
    new_medoids = compute_medoids(new_embeddings, new_labels)

    # Build a FAISS index of old medoid embeddings
    old_medoid_embeddings = np.stack(
        [old_embeddings[idx] for idx in old_medoids.values()]
    ).astype(np.float32)
    old_medoid_labels = list(old_medoids.keys())

    index = faiss.IndexFlatIP(old_medoid_embeddings.shape[1])  # type: ignore[call-arg]
    index.add(old_medoid_embeddings)  # type: ignore[call-arg]

    matched: dict[int, str] = {}
    used_old_uuids: set[str] = set()

    for new_label, new_medoid_idx in sorted(new_medoids.items()):
        query = new_embeddings[new_medoid_idx : new_medoid_idx + 1].astype(np.float32)
        similarities, indices = index.search(query, 1)  # type: ignore[call-arg]

        if indices[0][0] >= 0:
            sim = float(similarities[0][0])
            cosine_dist = 1.0 - sim
            old_label = old_medoid_labels[indices[0][0]]
            old_uuid = old_cluster_ids.get(old_label)

            if (
                old_uuid is not None
                and cosine_dist <= threshold
                and old_uuid not in used_old_uuids
            ):
                matched[new_label] = old_uuid
                used_old_uuids.add(old_uuid)

    return matched
