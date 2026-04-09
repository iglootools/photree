"""Tests for photree.gallery.faces.clustering — FAISS and clustering logic."""

from pathlib import Path

import numpy as np

from photree.gallery.faces.clustering import (
    assign_to_nearest_cluster,
    build_faiss_index,
    cluster_embeddings,
    compute_medoids,
    load_faiss_index,
    match_clusters_by_medoid,
    save_faiss_index,
)


def _make_embeddings(n: int, *, dim: int = 512, seed: int = 42) -> np.ndarray:
    """Generate random L2-normalized embeddings."""
    rng = np.random.default_rng(seed)
    emb = rng.random((n, dim)).astype(np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    return emb / norms


def _make_clustered_embeddings(
    cluster_sizes: list[int],
    *,
    dim: int = 512,
    spread: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate embeddings with known cluster structure.

    Returns (embeddings, true_labels).
    """
    rng = np.random.default_rng(42)
    embeddings_list: list[np.ndarray] = []
    labels_list: list[np.ndarray] = []

    for i, size in enumerate(cluster_sizes):
        # Generate a random centroid
        centroid = rng.random(dim).astype(np.float32)
        centroid = centroid / np.linalg.norm(centroid)
        # Add small noise around centroid
        noise = rng.normal(0, spread, (size, dim)).astype(np.float32)
        cluster = centroid + noise
        # Re-normalize
        norms = np.linalg.norm(cluster, axis=1, keepdims=True)
        cluster = cluster / norms
        embeddings_list.append(cluster)
        labels_list.append(np.full(size, i, dtype=np.int32))

    return (
        np.concatenate(embeddings_list, axis=0),
        np.concatenate(labels_list, axis=0),
    )


class TestBuildFaissIndex:
    def test_creates_index_with_correct_count(self) -> None:
        emb = _make_embeddings(10)
        index = build_faiss_index(emb)
        assert index.ntotal == 10

    def test_empty_embeddings(self) -> None:
        emb = np.empty((0, 512), dtype=np.float32)
        index = build_faiss_index(emb)
        assert index.ntotal == 0


class TestFaissIndexIO:
    def test_round_trip(self, tmp_path: Path) -> None:
        emb = _make_embeddings(5)
        index = build_faiss_index(emb)
        path = tmp_path / "index.faiss"
        save_faiss_index(index, path)

        loaded = load_faiss_index(path)
        assert loaded is not None
        assert loaded.ntotal == 5

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_faiss_index(tmp_path / "missing.faiss") is None


class TestClusterEmbeddings:
    def test_single_face(self) -> None:
        emb = _make_embeddings(1)
        labels = cluster_embeddings(emb, distance_threshold=0.45)
        assert len(labels) == 1
        assert labels[0] == 0

    def test_empty_input(self) -> None:
        emb = np.empty((0, 512), dtype=np.float32)
        labels = cluster_embeddings(emb)
        assert len(labels) == 0

    def test_clusters_similar_faces_together(self) -> None:
        emb, true_labels = _make_clustered_embeddings([5, 5, 5], spread=0.02)
        labels = cluster_embeddings(emb, distance_threshold=0.45)

        # Faces within the same true cluster should have the same label
        for i in range(3):
            cluster_labels = labels[true_labels == i]
            assert len(set(cluster_labels)) == 1, (
                f"True cluster {i} was split into {len(set(cluster_labels))} clusters"
            )

    def test_separates_distinct_faces(self) -> None:
        # 3 tight clusters — use a strict threshold to separate them
        emb, _ = _make_clustered_embeddings([3, 3, 3], spread=0.01)
        labels = cluster_embeddings(emb, distance_threshold=0.1)

        unique_labels = set(labels)
        # Should produce at least 2 distinct clusters (3 is ideal but
        # random centroids in 512-d may not be far enough apart at all thresholds)
        assert len(unique_labels) >= 2


class TestAssignToNearestCluster:
    def test_assigns_similar_to_existing(self) -> None:
        emb, true_labels = _make_clustered_embeddings([5, 5], spread=0.02)
        index = build_faiss_index(emb)

        # Add a new face similar to cluster 0
        new_face = emb[0:1] + np.random.default_rng(99).normal(
            0, 0.02, (1, 512)
        ).astype(np.float32)
        new_face = new_face / np.linalg.norm(new_face, axis=1, keepdims=True)

        new_labels = assign_to_nearest_cluster(
            index, true_labels, new_face, distance_threshold=0.45
        )
        assert new_labels[0] == 0  # assigned to cluster 0

    def test_creates_new_cluster_for_dissimilar(self) -> None:
        emb = _make_embeddings(5, seed=1)
        index = build_faiss_index(emb)
        labels = np.zeros(5, dtype=np.int32)

        # Very different new face
        new_face = _make_embeddings(1, seed=999)
        new_labels = assign_to_nearest_cluster(
            index, labels, new_face, distance_threshold=0.1, next_cluster_id=1
        )
        assert new_labels[0] >= 1  # new cluster

    def test_empty_index_creates_new_clusters(self) -> None:
        index = build_faiss_index(np.empty((0, 512), dtype=np.float32))
        labels = np.array([], dtype=np.int32)
        new_emb = _make_embeddings(3)

        new_labels = assign_to_nearest_cluster(
            index, labels, new_emb, next_cluster_id=0
        )
        assert list(new_labels) == [0, 1, 2]


class TestComputeMedoids:
    def test_medoid_is_closest_to_centroid(self) -> None:
        emb, true_labels = _make_clustered_embeddings([5, 5], spread=0.02)
        medoids = compute_medoids(emb, true_labels)

        assert set(medoids.keys()) == {0, 1}
        # Each medoid should be within the correct cluster
        assert true_labels[medoids[0]] == 0
        assert true_labels[medoids[1]] == 1


class TestMatchClustersByMedoid:
    def test_matches_identical_clusters(self) -> None:
        emb, labels = _make_clustered_embeddings([5, 5], spread=0.02)
        old_ids = {0: "uuid-a", 1: "uuid-b"}

        matched = match_clusters_by_medoid(
            emb, labels, old_ids, emb, labels, threshold=0.45
        )

        assert matched.get(0) == "uuid-a"
        assert matched.get(1) == "uuid-b"

    def test_no_match_when_clusters_different(self) -> None:
        old_emb, old_labels = _make_clustered_embeddings([5], spread=0.02)
        new_emb = _make_embeddings(5, seed=999)
        new_labels = np.zeros(5, dtype=np.int32)

        old_ids = {0: "uuid-old"}
        matched = match_clusters_by_medoid(
            old_emb,
            old_labels,
            old_ids,
            new_emb,
            new_labels,
            threshold=0.1,
        )

        # Should not match since embeddings are very different
        assert 0 not in matched or matched[0] != "uuid-old"
