"""Tests for photree.album.faces.refresh module — change detection logic."""

from pathlib import Path

from photree.album.faces.protocol import (
    FaceProcessedKey,
    FaceProcessingState,
)
from photree.album.faces.refresh import (
    _keys_needing_processing,
    _needs_processing,
    refresh_face_data,
)


def _make_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("data")


def _make_ios_source(album_dir: Path) -> None:
    """Create a minimal iOS media source so it is discovered."""
    _make_file(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")


class TestAnalyzerInjection:
    def test_no_factory_skips_detection(self, tmp_path: Path) -> None:
        """With no injected factory, face detection is skipped entirely."""
        _make_ios_source(tmp_path)

        result = refresh_face_data(tmp_path, analyzer_factory=None)

        assert result.by_media_source == ()
        assert not (tmp_path / ".photree" / "cache" / "faces").exists()

    def test_factory_not_invoked_without_processable_images(
        self, tmp_path: Path
    ) -> None:
        """The factory is lazy: placeholder files yield no thumbnails, so the
        model is never built."""
        _make_ios_source(tmp_path)

        def _factory():
            raise AssertionError("analyzer factory should not be invoked")

        # Placeholder bytes can't be converted to a thumbnail, so detection is
        # skipped before the factory is ever called.
        refresh_face_data(tmp_path, analyzer_factory=_factory)


class TestNeedsProcessing:
    def test_new_key_needs_processing(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        (orig_dir / "IMG_0410.HEIC").write_text("data")

        state = FaceProcessingState()
        assert _needs_processing("0410", "IMG_0410.HEIC", orig_dir, state)

    def test_unchanged_file_skipped(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        src = orig_dir / "IMG_0410.HEIC"
        src.write_text("data")

        state = FaceProcessingState(
            processed_keys={
                "0410": FaceProcessedKey(
                    mtime=src.stat().st_mtime,
                    file_name="IMG_0410.HEIC",
                    face_count=1,
                    orig_width=4032,
                    orig_height=3024,
                    thumb_width=640,
                    thumb_height=480,
                ),
            }
        )
        assert not _needs_processing("0410", "IMG_0410.HEIC", orig_dir, state)

    def test_changed_mtime_needs_processing(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        (orig_dir / "IMG_0410.HEIC").write_text("data")

        state = FaceProcessingState(
            processed_keys={
                "0410": FaceProcessedKey(
                    mtime=0.0,  # different from actual mtime
                    file_name="IMG_0410.HEIC",
                    face_count=1,
                    orig_width=4032,
                    orig_height=3024,
                    thumb_width=640,
                    thumb_height=480,
                ),
            }
        )
        assert _needs_processing("0410", "IMG_0410.HEIC", orig_dir, state)


class TestKeysNeedingProcessing:
    def test_redetect_returns_all_keys(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        (orig_dir / "IMG_0410.HEIC").write_text("data")

        files = {"0410": "IMG_0410.HEIC", "0411": "IMG_0411.HEIC"}
        state = FaceProcessingState()
        result = _keys_needing_processing(
            files, orig_dir, state, model_changed=False, redetect=True
        )
        assert result == ["0410", "0411"]

    def test_model_changed_returns_all_keys(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()

        files = {"0410": "IMG_0410.HEIC"}
        state = FaceProcessingState()
        result = _keys_needing_processing(
            files, orig_dir, state, model_changed=True, redetect=False
        )
        assert result == ["0410"]

    def test_incremental_returns_only_new(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        src = orig_dir / "IMG_0410.HEIC"
        src.write_text("data")
        (orig_dir / "IMG_0411.HEIC").write_text("data2")

        state = FaceProcessingState(
            processed_keys={
                "0410": FaceProcessedKey(
                    mtime=src.stat().st_mtime,
                    file_name="IMG_0410.HEIC",
                    face_count=1,
                    orig_width=4032,
                    orig_height=3024,
                    thumb_width=640,
                    thumb_height=480,
                ),
            }
        )
        result = _keys_needing_processing(
            {"0410": "IMG_0410.HEIC", "0411": "IMG_0411.HEIC"},
            orig_dir,
            state,
            model_changed=False,
            redetect=False,
        )
        assert result == ["0411"]
