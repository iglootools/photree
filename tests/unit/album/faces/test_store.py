"""Tests for photree.album.faces.store module."""

from pathlib import Path

import numpy as np

from photree.album.faces.protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessedKey,
    FaceProcessingState,
)
from photree.album.faces.store import (
    FaceData,
    filter_face_data,
    load_face_data,
    load_face_state,
    merge_face_data,
    save_face_data,
    save_face_state,
)


def _sample_face_data(keys: list[str], face_indices: list[int]) -> FaceData:
    """Build a small FaceData with deterministic embeddings for testing."""
    n = len(keys)
    return FaceData(
        keys=np.array(keys, dtype=object),
        face_indices=np.array(face_indices, dtype=np.int32),
        det_scores=np.full(n, 0.95, dtype=np.float32),
        bboxes=np.zeros((n, 4), dtype=np.float32),
        landmarks=np.zeros((n, 5, 2), dtype=np.float32),
        embeddings=np.random.default_rng(42).random((n, 512)).astype(np.float32),
    )


class TestFaceData:
    def test_empty(self) -> None:
        data = FaceData.empty()
        assert data.count == 0
        assert data.embeddings.shape == (0, 512)

    def test_count(self) -> None:
        data = _sample_face_data(["0410", "0410", "0411"], [0, 1, 0])
        assert data.count == 3


class TestFaceDataIO:
    def test_round_trip(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        original = _sample_face_data(["0410", "0411"], [0, 0])

        save_face_data(album, "main", original)
        loaded = load_face_data(album, "main")

        assert loaded is not None
        assert loaded.count == 2
        np.testing.assert_array_equal(loaded.keys, original.keys)
        np.testing.assert_array_equal(loaded.face_indices, original.face_indices)
        np.testing.assert_array_almost_equal(loaded.embeddings, original.embeddings)

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_face_data(tmp_path, "main") is None


class TestFaceStateIO:
    def test_round_trip(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        state = FaceProcessingState(
            model_name=DEFAULT_MODEL_NAME,
            model_version=DEFAULT_MODEL_VERSION,
            processed_keys={
                "0410": FaceProcessedKey(
                    mtime=1712345678.123,
                    file_name="IMG_0410.HEIC",
                    face_count=2,
                    orig_width=4032,
                    orig_height=3024,
                    thumb_width=640,
                    thumb_height=480,
                ),
            },
        )

        save_face_state(album, "main", state)
        loaded = load_face_state(album, "main")

        assert loaded is not None
        assert loaded.model_name == DEFAULT_MODEL_NAME
        assert "0410" in loaded.processed_keys
        assert loaded.processed_keys["0410"].face_count == 2
        assert loaded.processed_keys["0410"].orig_width == 4032

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_face_state(tmp_path, "main") is None


class TestFilterFaceData:
    def test_keeps_only_matching_keys(self) -> None:
        data = _sample_face_data(["0410", "0410", "0411", "0412"], [0, 1, 0, 0])
        filtered = filter_face_data(data, keep_keys={"0410", "0412"})

        assert filtered.count == 3
        assert set(filtered.keys) == {"0410", "0412"}

    def test_empty_keep_keys_returns_empty(self) -> None:
        data = _sample_face_data(["0410"], [0])
        filtered = filter_face_data(data, keep_keys=set())
        assert filtered.count == 0

    def test_filter_empty_data_returns_empty(self) -> None:
        data = FaceData.empty()
        filtered = filter_face_data(data, keep_keys={"0410"})
        assert filtered.count == 0


class TestMergeFaceData:
    def test_merges_two_datasets(self) -> None:
        a = _sample_face_data(["0410"], [0])
        b = _sample_face_data(["0411", "0412"], [0, 0])
        merged = merge_face_data(a, b)

        assert merged.count == 3
        assert list(merged.keys) == ["0410", "0411", "0412"]

    def test_merge_with_empty_returns_other(self) -> None:
        data = _sample_face_data(["0410"], [0])
        assert merge_face_data(FaceData.empty(), data).count == 1
        assert merge_face_data(data, FaceData.empty()).count == 1
