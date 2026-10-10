"""Tests for gallery face clustering refresh and its consistency check."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from photree.album.faces.store import FaceData, save_face_data
from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.fsprotocol import (
    GalleryMetadata,
    InvalidMetadataError,
    save_gallery_metadata,
)
from photree.gallery.faces.check import AlbumFaceDataNotIndexed, check_face_clusters
from photree.gallery.faces.face_refresh import (
    FACE_REFRESH_STAGES,
    FaceRefreshMode,
    refresh_face_clusters,
)
from photree.gallery.faces.manifest import (
    clusters_path,
    faiss_index_path,
    load_clusters,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata())
    return gallery


def _embedding(axis: int) -> np.ndarray:
    vec = np.zeros(512, dtype=np.float32)
    vec[axis] = 1.0
    return vec


def _setup_album_with_faces(gallery: Path, name: str, axes: list[int]) -> Path:
    album_dir = gallery / "albums" / "2024" / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    n = len(axes)
    save_face_data(
        album_dir,
        "main",
        FaceData(
            keys=np.array(["0001"] * n, dtype=object),
            face_indices=np.arange(n, dtype=np.int32),
            det_scores=np.ones(n, dtype=np.float32),
            bboxes=np.zeros((n, 4), dtype=np.float32),
            landmarks=np.zeros((n, 5, 2), dtype=np.float32),
            embeddings=np.stack([_embedding(a) for a in axes]),
        ),
    )
    return album_dir


def _counter_ids() -> Callable[[], str]:
    ids = (f"cluster-{i}" for i in range(1000))
    return lambda: next(ids)


class TestThreshold:
    def test_zero_threshold_is_not_replaced_by_default(self, tmp_path: Path) -> None:
        """Regression: ``0.0 or DEFAULT`` turned the strictest threshold into 0.45."""
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0, 1])

        first = refresh_face_clusters(gallery, distance_threshold=0.0)
        second = refresh_face_clusters(gallery, distance_threshold=0.0)

        clusters = load_clusters(gallery)
        assert clusters is not None and clusters.threshold == 0.0
        assert first.mode is FaceRefreshMode.FULL
        # Same threshold again: nothing to do (no spurious full re-cluster).
        assert second.mode is FaceRefreshMode.NONE


class TestCorruptState:
    def test_corrupt_clusters_file_raises(self, tmp_path: Path) -> None:
        """Regression: an empty clusters.yaml read as absent and lost UUIDs."""
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0])
        refresh_face_clusters(gallery)
        clusters_path(gallery).write_text("", encoding="utf-8")

        with pytest.raises(InvalidMetadataError) as exc_info:
            refresh_face_clusters(gallery, force_full=True)

        assert exc_info.value.path == clusters_path(gallery)


class TestStages:
    def test_missing_index_runs_full_cluster_with_real_callbacks(
        self, tmp_path: Path
    ) -> None:
        """Regression: the fallback full re-cluster silenced stage callbacks."""
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0])
        refresh_face_clusters(gallery)
        faiss_index_path(gallery).unlink()
        _setup_album_with_faces(gallery, "2024-07-15 - Beach", [1])

        started: list[str] = []
        ended: list[str] = []
        result = refresh_face_clusters(
            gallery, on_stage_start=started.append, on_stage_end=ended.append
        )

        assert result.mode is FaceRefreshMode.FULL
        assert result.total_faces == 2
        assert started == list(FACE_REFRESH_STAGES)
        assert ended == list(FACE_REFRESH_STAGES)

    def test_uses_injected_cluster_ids(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0, 1])

        refresh_face_clusters(gallery, new_id=_counter_ids())

        clusters = load_clusters(gallery)
        assert clusters is not None
        assert sorted(c.id for c in clusters.clusters) == ["cluster-0", "cluster-1"]


class TestCheckFaceClusters:
    def test_reports_album_face_data_missing_from_index(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0])
        refresh_face_clusters(gallery)
        added = _setup_album_with_faces(gallery, "2024-07-15 - Beach", [1])

        result = check_face_clusters(gallery)

        assert result is not None
        assert result.issues == (AlbumFaceDataNotIndexed(added, "main"),)

    def test_no_clustering_data_is_not_checked(self, tmp_path: Path) -> None:
        assert check_face_clusters(_setup_gallery(tmp_path)) is None
