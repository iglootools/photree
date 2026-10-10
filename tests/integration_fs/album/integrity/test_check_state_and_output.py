"""Regression tests for check state detection and integrity output."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from photree.album.check import AlbumIntegrityResult
from photree.album.check.exif_cache_state import check_exif_cache_state
from photree.album.check.face_state import (
    FaceSyncIssue,
    FaceSyncIssueKind,
    check_face_state,
)
from photree.album.check.output import (
    format_album_preflight_troubleshoot,
    format_exif_cache_check,
    format_integrity_checks,
)
from photree.album.check.testkit import (
    IOS_INTEGRITY_OK,
    PREFLIGHT_OK,
    STD_INTEGRITY_FAILURES,
)
from photree.album.faces.protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessedKey,
    FaceProcessingState,
)
from photree.album.faces.store import FaceData, save_face_data, save_face_state
from photree.album.store.media_source import ios_media_source, std_media_source
from photree.foundation.layout import PHOTREE_DIR

MAIN = ios_media_source("main")


def _state(face_count: int) -> FaceProcessingState:
    return FaceProcessingState(
        model_name=DEFAULT_MODEL_NAME,
        model_version=DEFAULT_MODEL_VERSION,
        processed_keys={
            "0410": FaceProcessedKey(
                mtime=1.0,
                file_name="IMG_0410.HEIC",
                face_count=face_count,
                orig_width=4032,
                orig_height=3024,
                thumb_width=640,
                thumb_height=480,
            )
        },
    )


def _face_data(keys: list[str]) -> FaceData:
    n = len(keys)
    return FaceData(
        keys=np.array(keys, dtype=object),
        face_indices=np.zeros(n, dtype=np.int32),
        det_scores=np.full(n, 0.9, dtype=np.float32),
        bboxes=np.zeros((n, 4), dtype=np.float32),
        landmarks=np.zeros((n, 5, 2), dtype=np.float32),
        embeddings=np.zeros((n, 512), dtype=np.float32),
    )


class TestFaceStateDesync:
    def test_in_sync(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=1))
        save_face_data(tmp_path, "main", _face_data(["0410"]))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.success

    def test_yaml_records_faces_but_npz_missing(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=2))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.npz_yaml_sync_errors == (
            FaceSyncIssue("main", FaceSyncIssueKind.MISSING_NPZ),
        )

    def test_yaml_without_faces_needs_no_npz(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=0))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.success

    def test_npz_without_yaml(self, tmp_path: Path) -> None:
        save_face_data(tmp_path, "main", _face_data(["0410"]))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.npz_yaml_sync_errors == (
            FaceSyncIssue("main", FaceSyncIssueKind.MISSING_YAML),
        )


class TestExifCacheState:
    def test_no_cache_dir_is_not_checked(self, tmp_path: Path) -> None:
        assert check_exif_cache_state(tmp_path, [MAIN]) is None

    def test_complete_cache_reports_success(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / PHOTREE_DIR / "cache" / "exif"
        cache_dir.mkdir(parents=True)
        (cache_dir / "main.yaml").write_text("files: {}\n", encoding="utf-8")

        check = check_exif_cache_state(tmp_path, [MAIN])

        assert check is not None
        assert check.success
        assert "exif cache" in format_exif_cache_check(check)


class TestIntegrityOutputLabels:
    def test_ios_labels_use_media_source_dirs(self) -> None:
        result = AlbumIntegrityResult(
            by_media_source=((ios_media_source("bruno"), IOS_INTEGRITY_OK),)
        )

        output = format_integrity_checks(result)

        assert "bruno-img" in output
        assert "bruno-vid" in output
        assert "bruno-jpg" in output
        assert "main-" not in output


class TestStdDuplicateStems:
    def test_duplicate_stems_are_printed(self) -> None:
        result = AlbumIntegrityResult(
            by_media_source=((std_media_source("nelu"), STD_INTEGRITY_FAILURES),)
        )

        output = format_integrity_checks(result)

        assert "duplicate stems" in output
        assert "stem photo2 has multiple media files" in output

    def test_std_failures_get_suggestions(self) -> None:
        preflight = replace(
            PREFLIGHT_OK,
            integrity=AlbumIntegrityResult(
                by_media_source=((std_media_source("nelu"), STD_INTEGRITY_FAILURES),)
            ),
        )

        troubleshoot = format_album_preflight_troubleshoot(preflight, "album")

        assert troubleshoot is not None
        assert "--refresh-browsable" in troubleshoot
        assert "sharing a stem" in troubleshoot
