import os
from pathlib import Path

import numpy as np
import pytest

from photree.album.faces.protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessedKey,
    FaceProcessingState,
)
from photree.album.faces.store import (
    FaceData,
    LegacyFaceDataError,
    data_path,
    filter_face_data,
    has_legacy_face_data,
    load_face_data,
    load_face_state,
    merge_face_data,
    read_face_count,
    save_face_data,
    save_face_state,
    state_path,
)
from photree.album.faces.testkit import write_legacy_face_data
from photree.foundation.metadata_io import InvalidMetadataError


def _sample_face_data(keys: list[str], face_indices: list[int]) -> FaceData:
    """Build a small FaceData with deterministic embeddings for testing."""
    n = len(keys)
    return FaceData(
        keys=np.array(keys, dtype=np.str_),
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


class _RunsCodeWhenUnpickled:
    """Unpickles by creating *marker*: proof that a reader unpickled it."""

    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def __reduce__(self) -> tuple[object, tuple[str]]:
        return (os.mkdir, (str(self.marker),))


def _write_booby_trapped_legacy_file(album: Path) -> Path:
    """Write a legacy file whose ``keys`` creates a marker when unpickled."""
    return write_legacy_face_data(
        album,
        "main",
        np.array([_RunsCodeWhenUnpickled(album / "unpickled")], dtype=object),
    )


class TestFaceDataFormat:
    def test_booby_trapped_file_runs_code_when_unpickled(self, tmp_path: Path) -> None:
        """Guard for the tests below: the trap does go off when unpickled."""
        path = _write_booby_trapped_legacy_file(tmp_path)

        with np.load(path, allow_pickle=True) as npz:
            npz["keys"]

        assert (tmp_path / "unpickled").exists()

    def test_keys_are_saved_as_unicode_not_objects(self, tmp_path: Path) -> None:
        save_face_data(tmp_path, "main", _sample_face_data(["0410"], [0]))

        with np.load(data_path(tmp_path, "main"), allow_pickle=False) as npz:
            assert npz["keys"].dtype.kind == "U"

    def test_object_keys_from_caller_are_saved_as_unicode(
        self,
        tmp_path: Path,
    ) -> None:
        data = _sample_face_data(["0410"], [0])

        save_face_data(
            tmp_path,
            "main",
            FaceData(**{**vars(data), "keys": data.keys.astype(object)}),
        )

        assert not has_legacy_face_data(tmp_path, "main")

    def test_legacy_file_is_rejected_without_unpickling(self, tmp_path: Path) -> None:
        _write_booby_trapped_legacy_file(tmp_path)

        with pytest.raises(LegacyFaceDataError) as exc_info:
            load_face_data(tmp_path, "main")

        assert exc_info.value.derived
        assert not (tmp_path / "unpickled").exists()

    def test_legacy_file_is_detected(self, tmp_path: Path) -> None:
        write_legacy_face_data(tmp_path, "main", np.array(["0410"]))

        assert has_legacy_face_data(tmp_path, "main")

    def test_missing_file_is_not_legacy(self, tmp_path: Path) -> None:
        assert not has_legacy_face_data(tmp_path, "main")

    def test_truncated_file_raises_as_derived(self, tmp_path: Path) -> None:
        save_face_data(tmp_path, "main", _sample_face_data(["0410"], [0]))
        path = data_path(tmp_path, "main")
        path.write_bytes(path.read_bytes()[:100])

        with pytest.raises(InvalidMetadataError) as exc_info:
            load_face_data(tmp_path, "main")

        assert exc_info.value.derived
        assert exc_info.value.path == path

    def test_file_without_keys_raises_as_derived(self, tmp_path: Path) -> None:
        path = data_path(tmp_path, "main")
        path.parent.mkdir(parents=True)
        np.savez_compressed(path, other=np.zeros(1))

        with pytest.raises(InvalidMetadataError) as exc_info:
            load_face_data(tmp_path, "main")

        assert exc_info.value.derived


class TestReadFaceCount:
    def test_counts_faces(self, tmp_path: Path) -> None:
        save_face_data(tmp_path, "main", _sample_face_data(["0410", "0410"], [0, 1]))

        assert read_face_count(data_path(tmp_path, "main")) == 2

    def test_counts_legacy_file_without_unpickling(self, tmp_path: Path) -> None:
        path = _write_booby_trapped_legacy_file(tmp_path)

        assert read_face_count(path) == 1
        assert not (tmp_path / "unpickled").exists()


class TestCorruptFaceState:
    def test_corrupt_state_raises_as_derived(self, tmp_path: Path) -> None:
        path = state_path(tmp_path, "main")
        path.parent.mkdir(parents=True)
        path.write_text("- not a mapping\n", encoding="utf-8")

        with pytest.raises(InvalidMetadataError) as exc_info:
            load_face_state(tmp_path, "main")

        assert exc_info.value.derived
