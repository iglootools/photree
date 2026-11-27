"""Tests for photree.albums.output.importer."""

from pathlib import Path

from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.importer.album_import import (
    EmptyImageCaptureDirError,
    NoImportTasksError,
)
from photree.album.importer.collision import (
    MediaSourceClash,
    MediaSourceClashError,
    MediaSourceClashErrorKind,
)
from photree.album.jpeg import JpegConversionFailure
from photree.album.store.media_source import std_media_source
from photree.albums.cmd_handler.importer import AlbumFailure
from photree.albums.output.importer import batch_failures, failure_reason


class TestFailureReason:
    def test_no_import_tasks_names_the_album_relative_to_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            error=NoImportTasksError(tmp_path / "A"),
        )

        assert failure_reason(failure, tmp_path) == (
            "No to-import-{ios,std}-<media-source> directories found in A"
        )

    def test_empty_image_capture_dir_names_the_directory_relative_to_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            error=EmptyImageCaptureDirError(tmp_path / "ic"),
        )

        assert failure_reason(failure, tmp_path) == (
            "Could not find any image capture files in ic"
        )

    def test_media_source_clash_is_worded_with_the_way_out(
        self,
        tmp_path: Path,
    ) -> None:
        ms = std_media_source("main")
        clash = MediaSourceClash(ms, MediaSourceClashErrorKind.EXISTING_ARCHIVE)
        failure = AlbumFailure(tmp_path / "A", error=MediaSourceClashError(clash))

        assert "Rename to-import-std-main" in failure_reason(failure, tmp_path)

    def test_filesystem_error_names_the_file_relative_to_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        error = PermissionError(13, "Permission denied", str(tmp_path / "A" / "x"))
        failure = AlbumFailure(tmp_path / "A", error=error)

        assert failure_reason(failure, tmp_path) == "Permission denied: A/x"

    def test_other_error_is_shown_as_raised(self, tmp_path: Path) -> None:
        failure = AlbumFailure(tmp_path / "A", error=ValueError("bad"))

        assert failure_reason(failure, tmp_path) == "bad"

    def test_failure_after_the_import_names_every_part_that_failed(
        self,
        tmp_path: Path,
    ) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            unprocessed=("IMG_0001.HEIC",),
            jpeg_failures=(("main", JpegConversionFailure("IMG_0002.HEIC", "bad")),),
            face_failures=(
                ("main", FaceFailure("0003", FaceFailureStage.DETECTION, "boom")),
            ),
        )

        assert failure_reason(failure, tmp_path) == (
            "selection entries left behind: IMG_0001.HEIC; "
            "jpeg conversion failed: main/IMG_0002.HEIC: bad; "
            "face detection failed: main/0003 (detection): boom"
        )

    def test_batch_failures_words_a_refusal(self, tmp_path: Path) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            error=EmptyImageCaptureDirError(tmp_path / "ic"),
        )

        assert "Could not find any image capture files in ic" in batch_failures(
            [failure],
            tmp_path,
        )
