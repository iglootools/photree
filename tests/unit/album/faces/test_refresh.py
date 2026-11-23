from pathlib import Path
from typing import Any, NoReturn

import cv2
import numpy as np
import pytest

from photree.album.faces.detect import ThumbnailResult
from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.faces.protocol import (
    FaceProcessedKey,
    FaceProcessingState,
)
from photree.album.faces.refresh import (
    FaceRefreshResult,
    FaceSourceRefreshResult,
    detect_single,
    keys_needing_processing,
    needs_processing,
    refresh_face_data,
    reuse_thumbnail,
)
from photree.album.faces.store import (
    data_path,
    has_legacy_face_data,
    load_face_data,
    load_face_state,
    save_face_state,
    state_path,
)
from photree.album.faces.testkit import write_legacy_face_data
from photree.foundation.metadata_io import InvalidMetadataError


def _make_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("data", encoding="utf-8")


def _make_ios_source(album_dir: Path) -> None:
    """Create a minimal iOS media source so it is discovered."""
    _make_file(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")


class TestAnalyzerInjection:
    def test_no_factory_skips_detection(self, tmp_path: Path) -> None:
        _make_ios_source(tmp_path)

        result = refresh_face_data(tmp_path, analyzer_factory=None)

        assert result.by_media_source == ()
        assert not (tmp_path / ".photree" / "cache" / "faces").exists()

    def test_factory_not_invoked_without_processable_images(
        self,
        tmp_path: Path,
    ) -> None:
        """
        Build no model when no source has processable images.

        The factory is lazy: placeholder files yield no thumbnails, so the
        model is never built.
        """
        _make_ios_source(tmp_path)

        def _factory() -> NoReturn:
            message = "analyzer factory should not be invoked"
            raise AssertionError(message)

        refresh_face_data(tmp_path, analyzer_factory=_factory)


class TestNeedsProcessing:
    def test_new_key_needs_processing(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        (orig_dir / "IMG_0410.HEIC").write_text("data")

        state = FaceProcessingState()
        assert needs_processing("0410", "IMG_0410.HEIC", orig_dir, state)

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
            },
        )
        assert not needs_processing("0410", "IMG_0410.HEIC", orig_dir, state)

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
            },
        )
        assert needs_processing("0410", "IMG_0410.HEIC", orig_dir, state)


class TestKeysNeedingProcessing:
    def test_redetect_returns_all_keys(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()
        (orig_dir / "IMG_0410.HEIC").write_text("data")

        files = {"0410": "IMG_0410.HEIC", "0411": "IMG_0411.HEIC"}
        state = FaceProcessingState()
        result = keys_needing_processing(
            files,
            orig_dir,
            state,
            model_changed=False,
            redetect=True,
        )
        assert result == ["0410", "0411"]

    def test_model_changed_returns_all_keys(self, tmp_path: Path) -> None:
        orig_dir = tmp_path / "orig-img"
        orig_dir.mkdir()

        files = {"0410": "IMG_0410.HEIC"}
        state = FaceProcessingState()
        result = keys_needing_processing(
            files,
            orig_dir,
            state,
            model_changed=True,
            redetect=False,
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
            },
        )
        result = keys_needing_processing(
            {"0410": "IMG_0410.HEIC", "0411": "IMG_0411.HEIC"},
            orig_dir,
            state,
            model_changed=False,
            redetect=False,
        )
        assert result == ["0411"]


class TestFailureReporting:
    """
    Per-image failures must carry a reason, not just a count.

    Detection is best-effort — one unreadable file must not abandon the album —
    but the reason used to be discarded by a bare ``except Exception``, and a
    thumbnail that failed made its key vanish entirely: never analysed, never
    counted, indistinguishable from an image with no faces.
    """

    def test_detection_failure_carries_key_stage_and_reason(self) -> None:
        class _Boom:
            def get(self, img: np.ndarray) -> list[Any]:  # noqa: ARG002 - FaceDetector's signature
                message = "model exploded"
                raise RuntimeError(message)

        tr = ThumbnailResult(
            key="0410",
            file_name="IMG_0410.HEIC",
            thumb_path=Path("/nonexistent/0410.jpg"),
            orig_width=4032,
            orig_height=3024,
        )

        faces, state_key, failure = detect_single(tr, Path("/nonexistent"), _Boom())

        assert faces is None
        assert state_key is None
        assert failure is not None
        assert failure.key == "0410"
        assert failure.stage == FaceFailureStage.DETECTION
        assert failure.reason

    def test_result_exposes_failures_per_media_source(self) -> None:
        failure = FaceFailure(
            key="0410",
            stage=FaceFailureStage.THUMBNAIL,
            reason="sips said no",
        )
        result = FaceRefreshResult(
            by_media_source=(
                (
                    "main",
                    FaceSourceRefreshResult(
                        processed=1,
                        skipped=0,
                        faces_detected=0,
                        failures=(failure,),
                    ),
                ),
                (
                    "bruno",
                    FaceSourceRefreshResult(processed=2, skipped=0, faces_detected=3),
                ),
            ),
        )

        assert result.failures == (("main", failure),)
        assert result.by_media_source[0][1].failed == 1
        assert result.by_media_source[1][1].failed == 0


class TestFailureAccounting:
    def test_unreadable_thumbnail_is_a_detection_failure(self, tmp_path: Path) -> None:
        """cv2 returning None used to read as "no faces"; it is a failure."""
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
        )

        class _NeverCalled:
            def get(self, img: np.ndarray) -> list[Any]:  # noqa: ARG002 - FaceDetector's signature
                message = "analyzer must not see an unreadable image"
                raise AssertionError(message)

        faces, state_key, failure = detect_single(tr, orig_dir, _NeverCalled())

        assert faces is None
        assert state_key is None
        assert failure is not None
        assert failure.stage == FaceFailureStage.DETECTION

    def test_failed_keys_are_not_counted_as_processed(self, tmp_path: Path) -> None:
        """Placeholder bytes cannot be thumbnailed: 1 failure, 0 processed."""
        _make_ios_source(tmp_path)

        def _factory() -> NoReturn:
            message = "analyzer factory should not be invoked"
            raise AssertionError(message)

        result = refresh_face_data(tmp_path, analyzer_factory=_factory)

        ((_, source),) = result.by_media_source
        assert source.processed == 0
        assert [f.key for f in source.failures] == ["0410"]
        assert source.failures[0].stage == FaceFailureStage.THUMBNAIL


class TestReuseThumbnail:
    def test_without_previous_state_is_a_failure(self, tmp_path: Path) -> None:
        result = reuse_thumbnail("0410", "IMG_0410.HEIC", tmp_path / "x.jpg", None)

        assert isinstance(result, FaceFailure)
        assert result.stage == FaceFailureStage.THUMBNAIL

    def test_keeps_original_dimensions_from_state(self, tmp_path: Path) -> None:
        """Reused thumbnails used to record a 0x0 original."""
        result = reuse_thumbnail(
            "0410",
            "IMG_0410.HEIC",
            tmp_path / "0410.jpg",
            _processed(4032, 3024),
        )

        assert isinstance(result, ThumbnailResult)
        assert (result.orig_width, result.orig_height) == (4032, 3024)


class TestDetectSingle:
    def test_records_thumbnail_size_from_decoded_image(self, tmp_path: Path) -> None:
        thumb = tmp_path / "0410.jpg"
        cv2.imwrite(str(thumb), np.zeros((48, 64, 3), dtype=np.uint8))
        orig_dir = tmp_path / "orig"
        _make_file(orig_dir / "IMG_0410.HEIC")
        tr = ThumbnailResult(
            key="0410",
            file_name="IMG_0410.HEIC",
            thumb_path=thumb,
            orig_width=4032,
            orig_height=3024,
        )

        class _NoFaces:
            def get(self, img: np.ndarray) -> list[Any]:  # noqa: ARG002 - FaceDetector's signature
                return []

        faces, state_key, failure = detect_single(tr, orig_dir, _NoFaces())

        assert (faces, failure) == ([], None)
        assert state_key is not None
        assert (state_key.thumb_width, state_key.thumb_height) == (64, 48)
        assert (state_key.orig_width, state_key.orig_height) == (4032, 3024)


def _processed(width: int, height: int, *, mtime: float = 1.0) -> FaceProcessedKey:
    return FaceProcessedKey(
        mtime=mtime,
        file_name="IMG_0410.HEIC",
        face_count=0,
        orig_width=width,
        orig_height=height,
        thumb_width=640,
        thumb_height=480,
    )


def _never_invoked_factory() -> NoReturn:
    message = "analyzer factory should not be invoked"
    raise AssertionError(message)


def _save_processed_state(album_dir: Path) -> None:
    """Record ``IMG_0410.HEIC`` as processed at its current mtime."""
    src = album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC"
    save_face_state(
        album_dir,
        "main",
        FaceProcessingState(
            processed_keys={"0410": _processed(4032, 3024, mtime=src.stat().st_mtime)},
        ),
    )


class TestCorruptOrLegacyCache:
    def test_redetect_replaces_corrupt_state(self, tmp_path: Path) -> None:
        _make_ios_source(tmp_path)
        _make_file(state_path(tmp_path, "main"))

        refresh_face_data(
            tmp_path,
            analyzer_factory=_never_invoked_factory,
            redetect=True,
        )

        assert load_face_state(tmp_path, "main") is not None

    def test_redetect_replaces_truncated_data(self, tmp_path: Path) -> None:
        _make_ios_source(tmp_path)
        _make_file(data_path(tmp_path, "main"))

        refresh_face_data(
            tmp_path,
            analyzer_factory=_never_invoked_factory,
            redetect=True,
        )

        assert load_face_data(tmp_path, "main") is not None

    def test_truncated_data_raises_as_derived_without_redetect(
        self,
        tmp_path: Path,
    ) -> None:
        _make_ios_source(tmp_path)
        _make_file(data_path(tmp_path, "main"))

        with pytest.raises(InvalidMetadataError) as exc_info:
            refresh_face_data(tmp_path, analyzer_factory=_never_invoked_factory)

        assert exc_info.value.derived

    def test_legacy_data_makes_every_image_due(self, tmp_path: Path) -> None:
        _make_ios_source(tmp_path)
        _save_processed_state(tmp_path)
        write_legacy_face_data(tmp_path, "main", np.array(["0410"]))

        result = refresh_face_data(
            tmp_path,
            analyzer_factory=_never_invoked_factory,
            dry_run=True,
        )

        ((_, source),) = result.by_media_source
        assert (source.processed, source.skipped) == (1, 0)

    def test_legacy_data_is_replaced(self, tmp_path: Path) -> None:
        _make_ios_source(tmp_path)
        _save_processed_state(tmp_path)
        write_legacy_face_data(tmp_path, "main", np.array(["0410"]))

        refresh_face_data(tmp_path, analyzer_factory=_never_invoked_factory)

        assert not has_legacy_face_data(tmp_path, "main")
