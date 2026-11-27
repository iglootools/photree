from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from photree.gallery.faces.clustering import (
    assign_to_nearest_cluster,
    build_faiss_index,
    build_knn_connectivity,
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
    """
    Generate embeddings with known cluster structure.

    Returns (embeddings, true_labels).
    """
    rng = np.random.default_rng(42)
    embeddings_list: list[np.ndarray] = []
    labels_list: list[np.ndarray] = []

    for i, size in enumerate(cluster_sizes):
        centroid = rng.random(dim).astype(np.float32)
        centroid = centroid / np.linalg.norm(centroid)
        noise = rng.normal(0, spread, (size, dim)).astype(np.float32)
        cluster = centroid + noise
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


class TestBuildKnnConnectivity:
    def test_links_each_face_to_its_nearest_neighbours_both_ways(self) -> None:
        emb = _make_embeddings(40)
        k = 4

        # scipy ships no type information, so the matrix's methods are unknown.
        connectivity = cast("Any", build_knn_connectivity(emb, k=k))

        nearest = np.argsort(-(emb @ emb.T), axis=1)[:, 1 : k + 1]
        expected = np.zeros((40, 40), dtype=np.int8)
        expected[np.repeat(np.arange(40), k), nearest.ravel()] = 1
        expected = np.maximum(expected, expected.T)
        assert np.array_equal(connectivity.toarray(), expected)


class TestAssignToNearestCluster:
    def test_assigns_similar_to_existing(self) -> None:
        emb, true_labels = _make_clustered_embeddings([5, 5], spread=0.02)
        index = build_faiss_index(emb)

        # Add a new face similar to cluster 0
        new_face = emb[0:1] + np.random.default_rng(99).normal(
            0,
            0.02,
            (1, 512),
        ).astype(np.float32)
        new_face = new_face / np.linalg.norm(new_face, axis=1, keepdims=True)

        new_labels = assign_to_nearest_cluster(
            index,
            true_labels,
            new_face,
            distance_threshold=0.45,
        )
        assert new_labels[0] == 0

    def test_creates_new_cluster_for_dissimilar(self) -> None:
        emb = _make_embeddings(5, seed=1)
        index = build_faiss_index(emb)
        labels = np.zeros(5, dtype=np.int32)

        # Very different new face
        new_face = _make_embeddings(1, seed=999)
        new_labels = assign_to_nearest_cluster(
            index,
            labels,
            new_face,
            distance_threshold=0.1,
            next_cluster_id=1,
        )
        assert new_labels[0] >= 1  # new cluster

    def test_empty_index_creates_new_clusters(self) -> None:
        index = build_faiss_index(np.empty((0, 512), dtype=np.float32))
        labels = np.array([], dtype=np.int32)
        new_emb = _make_embeddings(3)

        new_labels = assign_to_nearest_cluster(
            index,
            labels,
            new_emb,
            next_cluster_id=0,
        )
        assert list(new_labels) == [0, 1, 2]


def _normalized(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize each row of *vectors*, as float32."""
    return (vectors / np.linalg.norm(vectors, axis=1, keepdims=True)).astype(
        np.float32,
    )


def _normal_embeddings(n: int, *, seed: int) -> np.ndarray:
    """Random L2-normalized embeddings spread over the whole sphere."""
    return _normalized(np.random.default_rng(seed).normal(size=(n, 512)))


def _reference_medoids(embeddings: np.ndarray, labels: np.ndarray) -> dict[int, int]:
    """Each cluster's face closest to its normalized centroid, one mask per label."""
    return {
        int(label): int(indices[np.argmax(members @ (centroid / norm))])
        for label in np.unique(labels)
        for indices in [np.where(labels == label)[0]]
        for members in [embeddings[indices]]
        for centroid in [members.mean(axis=0)]
        for norm in [np.linalg.norm(centroid) + 1e-10]
    }


def _reference_matching(
    old: tuple[np.ndarray, np.ndarray, dict[int, str]],
    new: tuple[np.ndarray, np.ndarray],
    threshold: float,
) -> dict[int, str]:
    """
    Match each new medoid, in label order, to the nearest unused old UUID.

    Brute force over every pair, as the greedy matching is specified.
    """
    old_emb, old_labels, old_ids = old
    new_emb, new_labels = new
    old_medoids = _reference_medoids(old_emb, old_labels)
    # Documented exception (docs/guidelines.md): loop-carried state, the UUIDs
    # earlier new clusters already took.
    matched: dict[int, str] = {}
    for new_label, new_idx in sorted(_reference_medoids(new_emb, new_labels).items()):
        similarities = {
            old_label: float(old_emb[old_idx] @ new_emb[new_idx])
            for old_label, old_idx in old_medoids.items()
        }
        uuid = next(
            (
                old_ids[old_label]
                for old_label in sorted(similarities, key=lambda o: -similarities[o])
                if old_label in old_ids
                and 1.0 - similarities[old_label] <= threshold
                and old_ids[old_label] not in matched.values()
            ),
            None,
        )
        if uuid is not None:
            matched[new_label] = uuid
    return matched


class TestComputeMedoids:
    def test_medoid_is_closest_to_centroid(self) -> None:
        emb, true_labels = _make_clustered_embeddings([5, 5], spread=0.02)
        medoids = compute_medoids(emb, true_labels)

        assert set(medoids.keys()) == {0, 1}
        assert true_labels[medoids[0]] == 0
        assert true_labels[medoids[1]] == 1

    def test_medoids_match_one_mask_per_label(self) -> None:
        emb = _normal_embeddings(400, seed=1)
        labels = np.random.default_rng(2).integers(0, 90, size=400).astype(np.int32)

        assert compute_medoids(emb, labels) == _reference_medoids(emb, labels)


class TestMatchClustersByMedoid:
    def test_matches_identical_clusters(self) -> None:
        emb, labels = _make_clustered_embeddings([5, 5], spread=0.02)
        old_ids = {0: "uuid-a", 1: "uuid-b"}

        matched = match_clusters_by_medoid(
            emb,
            labels,
            old_ids,
            emb,
            labels,
            threshold=0.45,
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

    def test_falls_back_to_next_nearest_old_cluster_when_nearest_is_taken(
        self,
    ) -> None:
        """Regression: only the nearest old medoid was tried, then a new UUID."""
        old_emb = np.eye(2, 512, dtype=np.float32)
        old_labels = np.array([0, 1], dtype=np.int32)
        # Both new clusters are nearest to old cluster A; the second one is still
        # within the threshold of old cluster B (cosine distance 0.4).
        new_emb = np.zeros((2, 512), dtype=np.float32)
        new_emb[0, 0] = 1.0
        new_emb[1, :2] = [0.8, 0.6]
        new_labels = np.array([0, 1], dtype=np.int32)

        matched = match_clusters_by_medoid(
            old_emb,
            old_labels,
            {0: "uuid-a", 1: "uuid-b"},
            new_emb,
            new_labels,
            threshold=0.45,
        )

        assert matched == {0: "uuid-a", 1: "uuid-b"}

    @pytest.mark.parametrize("threshold", [0.45, 0.9, 2.0])
    def test_matches_the_greedy_nearest_unused_uuid_of_every_new_cluster(
        self,
        threshold: float,
    ) -> None:
        old_emb = _normal_embeddings(600, seed=3)
        old_labels = np.random.default_rng(4).integers(0, 120, 600).astype(np.int32)
        # Some old clusters have no UUID, and the new faces are the old ones moved
        # a little and regrouped, so new clusters compete for the same old UUIDs.
        old_ids = {label: f"uuid-{label}" for label in range(120) if label % 7 != 0}
        noisy = old_emb + np.random.default_rng(5).normal(0, 0.03, old_emb.shape)
        new_emb = _normalized(noisy)
        new_labels = (old_labels * 3 // 4).astype(np.int32)

        matched = match_clusters_by_medoid(
            old_emb,
            old_labels,
            old_ids,
            new_emb,
            new_labels,
            threshold=threshold,
        )

        assert matched == _reference_matching(
            (old_emb, old_labels, old_ids),
            (new_emb, new_labels),
            threshold,
        )
        assert matched

    def test_new_clusters_all_nearest_the_same_old_ones_take_every_old_uuid(
        self,
    ) -> None:
        """More new clusters compete for the same old UUIDs than one search lists."""
        old_emb = _normal_embeddings(20, seed=6)
        old_labels = np.arange(20, dtype=np.int32)
        old_ids = {label: f"uuid-{label}" for label in range(20)}
        noisy = old_emb[0] + np.random.default_rng(7).normal(0, 0.01, (20, 512))
        new_emb = _normalized(noisy)

        matched = match_clusters_by_medoid(
            old_emb,
            old_labels,
            old_ids,
            new_emb,
            old_labels,
            threshold=2.0,
        )

        assert matched == _reference_matching(
            (old_emb, old_labels, old_ids),
            (new_emb, old_labels),
            2.0,
        )
        assert sorted(matched.values()) == sorted(old_ids.values())
