"""Tests for photree.album.faces.refresh module — change detection logic."""

import shutil
from pathlib import Path

import pytest

from photree.album.faces.failures import FaceFailureStage
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
    path.write_text("data", encoding="utf-8")


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


class TestFailureReporting:
    """Per-image failures must carry a reason, not just a count.

    Detection is best-effort — one unreadable file must not abandon the album —
    but the reason used to be discarded by a bare ``except Exception``, and a
    thumbnail that failed made its key vanish entirely: never analysed, never
    counted, indistinguishable from an image with no faces.
    """

    def test_detection_failure_carries_key_stage_and_reason(self) -> None:
        from photree.album.faces.detect import ThumbnailResult
        from photree.album.faces.refresh import _detect_single

        class _Boom:
            def get(self, *_args, **_kwargs):
                raise RuntimeError("model exploded")

        tr = ThumbnailResult(
            key="0410",
            file_name="IMG_0410.HEIC",
            thumb_path=Path("/nonexistent/0410.jpg"),
            orig_width=4032,
            orig_height=3024,
            thumb_width=640,
            thumb_height=480,
        )

        faces, state_key, failure = _detect_single(tr, Path("/nonexistent"), _Boom())

        assert faces is None
        assert state_key is None
        assert failure is not None
        assert failure.key == "0410"
        assert failure.stage == FaceFailureStage.DETECTION
        assert failure.reason

    def test_result_exposes_failures_per_media_source(self) -> None:
        from photree.album.faces.failures import FaceFailure
        from photree.album.faces.refresh import (
            FaceRefreshResult,
            FaceSourceRefreshResult,
        )

        failure = FaceFailure(
            key="0410", stage=FaceFailureStage.THUMBNAIL, reason="sips said no"
        )
        result = FaceRefreshResult(
            by_media_source=(
                (
                    "main",
                    FaceSourceRefreshResult(
                        processed=1, skipped=0, faces_detected=0, failures=(failure,)
                    ),
                ),
                (
                    "bruno",
                    FaceSourceRefreshResult(processed=2, skipped=0, faces_detected=3),
                ),
            )
        )

        assert result.failures == (("main", failure),)
        assert result.by_media_source[0][1].failed == 1
        assert result.by_media_source[1][1].failed == 0


class TestFailureAccounting:
    def test_unreadable_thumbnail_is_a_detection_failure(self, tmp_path: Path) -> None:
        """cv2 returning None used to read as "no faces"; it is a failure."""
        from photree.album.faces.detect import ThumbnailResult
        from photree.album.faces.refresh import _detect_single

        thumb = tmp_path / "0410.jpg"
        thumb.write_text("not a jpeg", encoding="utf-8")
        orig_dir = tmp_path / "orig"
        _make_file(orig_dir / "IMG_0410.HEIC")
        tr = ThumbnailResult(
            key="0410",
            file_name="IMG_0410.HEIC",
            thumb_path=thumb,
            orig_width=4032,
            orig_height=3024,
            thumb_width=640,
            thumb_height=480,
        )

        class _NeverCalled:
            def get(self, *_args, **_kwargs):
                raise AssertionError("analyzer must not see an unreadable image")

        faces, state_key, failure = _detect_single(tr, orig_dir, _NeverCalled())

        assert faces is None and state_key is None
        assert failure is not None
        assert failure.stage == FaceFailureStage.DETECTION

    def test_failed_keys_are_not_counted_as_processed(self, tmp_path: Path) -> None:
        """Placeholder bytes cannot be thumbnailed: 1 failure, 0 processed."""
        _make_ios_source(tmp_path)

        def _factory():
            raise AssertionError("analyzer factory should not be invoked")

        result = refresh_face_data(tmp_path, analyzer_factory=_factory)

        ((_, source),) = result.by_media_source
        assert source.processed == 0
        assert [f.key for f in source.failures] == ["0410"]
        assert source.failures[0].stage == FaceFailureStage.THUMBNAIL


class TestReuseThumbnail:
    def test_without_previous_state_is_a_failure(self, tmp_path: Path) -> None:
        from photree.album.faces.failures import FaceFailure
        from photree.album.faces.refresh import _reuse_thumbnail

        result = _reuse_thumbnail("0410", "IMG_0410.HEIC", tmp_path / "x.jpg", None)

        assert isinstance(result, FaceFailure)
        assert result.stage == FaceFailureStage.THUMBNAIL

    def test_unreadable_thumbnail_is_a_failure_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        from photree.album.faces.failures import FaceFailure
        from photree.album.faces.refresh import _reuse_thumbnail

        thumb = tmp_path / "0410.jpg"
        thumb.write_text("not a jpeg", encoding="utf-8")

        result = _reuse_thumbnail(
            "0410", "IMG_0410.HEIC", thumb, _processed(4032, 3024)
        )

        assert isinstance(result, FaceFailure)

    @pytest.mark.skipif(shutil.which("sips") is None, reason="needs macOS sips")
    def test_keeps_original_dimensions_from_state(self, tmp_path: Path) -> None:
        """Reused thumbnails used to record a 0x0 original."""
        import cv2
        import numpy as np

        from photree.album.faces.detect import ThumbnailResult
        from photree.album.faces.refresh import _reuse_thumbnail

        thumb = tmp_path / "0410.jpg"
        cv2.imwrite(str(thumb), np.zeros((48, 64, 3), dtype=np.uint8))

        result = _reuse_thumbnail(
            "0410", "IMG_0410.HEIC", thumb, _processed(4032, 3024)
        )

        assert isinstance(result, ThumbnailResult)
        assert (result.orig_width, result.orig_height) == (4032, 3024)
        assert (result.thumb_width, result.thumb_height) == (64, 48)


def _processed(width: int, height: int) -> FaceProcessedKey:
    return FaceProcessedKey(
        mtime=1.0,
        file_name="IMG_0410.HEIC",
        face_count=0,
        orig_width=width,
        orig_height=height,
        thumb_width=640,
        thumb_height=480,
    )
