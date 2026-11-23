from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from photree.album.faces.store import FaceData, save_face_data
from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.metadata_io import InvalidMetadataError
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
            embeddings=np.array([_embedding(a) for a in axes]).reshape(n, 512),
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
        assert clusters is not None
        assert clusters.threshold == 0.0
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
        self,
        tmp_path: Path,
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
            gallery,
            on_stage_start=started.append,
            on_stage_end=ended.append,
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


def _faces_by_cluster_id(gallery: Path) -> dict[str, list[int]]:
    clusters = load_clusters(gallery)
    assert clusters is not None
    return {c.id: c.face_indices for c in clusters.clusters}


def _assert_check_passes(gallery: Path) -> None:
    check = check_face_clusters(gallery)
    assert check is not None
    assert check.issues == ()


class TestIncrementalRefresh:
    def test_new_faces_join_existing_clusters_and_keep_their_ids(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0, 1])
        new_id = _counter_ids()
        refresh_face_clusters(gallery, new_id=new_id)
        before = _faces_by_cluster_id(gallery)
        _setup_album_with_faces(gallery, "2024-07-15 - Beach", [0, 2])

        result = refresh_face_clusters(gallery, new_id=new_id)

        (same_person_id,) = (cid for cid, faces in before.items() if 0 in faces)
        assert result.mode is FaceRefreshMode.INCREMENTAL
        assert (result.total_faces, result.new_faces) == (4, 2)
        assert _faces_by_cluster_id(gallery) == {
            **before,
            same_person_id: [*before[same_person_id], 2],
            "cluster-2": [3],
        }
        _assert_check_passes(gallery)

    def test_refresh_after_incremental_refresh_does_nothing(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0])
        refresh_face_clusters(gallery)
        _setup_album_with_faces(gallery, "2024-07-15 - Beach", [1])
        refresh_face_clusters(gallery)

        result = refresh_face_clusters(gallery)

        assert result.mode is FaceRefreshMode.NONE
        assert result.total_faces == 2

    def test_album_without_faces_is_recorded_as_ingested(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: a faceless album stayed new forever and failed the check."""
        gallery = _setup_gallery(tmp_path)
        _setup_album_with_faces(gallery, "2024-07-14 - Trip", [0])
        refresh_face_clusters(gallery)
        _setup_album_with_faces(gallery, "2024-07-15 - Landscapes", [])

        first = refresh_face_clusters(gallery)
        second = refresh_face_clusters(gallery)

        assert first.mode is FaceRefreshMode.INCREMENTAL
        assert second.mode is FaceRefreshMode.NONE
        _assert_check_passes(gallery)
