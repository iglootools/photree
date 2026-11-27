"""Tests for photree.albums.output.importer."""

from pathlib import Path

from photree.album.importer.album_import import (
    EmptyImageCaptureDirError,
    NoImportTasksError,
)
from photree.albums.cmd_handler.importer import AlbumFailure, ImportFailureStage
from photree.albums.output.importer import batch_failures, failure_reason


class TestFailureReason:
    def test_no_import_tasks_names_the_album_relative_to_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            reason="",
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
            reason="",
            error=EmptyImageCaptureDirError(tmp_path / "ic"),
        )

        assert failure_reason(failure, tmp_path) == (
            "Could not find any image capture files in ic"
        )

    def test_filesystem_error_names_the_file_relative_to_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        error = PermissionError(13, "Permission denied", str(tmp_path / "A" / "x"))
        failure = AlbumFailure(tmp_path / "A", reason="", error=error)

        assert failure_reason(failure, tmp_path) == "Permission denied: A/x"

    def test_other_error_is_shown_as_raised(self, tmp_path: Path) -> None:
        failure = AlbumFailure(tmp_path / "A", reason="", error=ValueError("bad"))

        assert failure_reason(failure, tmp_path) == "bad"

    def test_failure_after_the_import_keeps_its_reason(self, tmp_path: Path) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            "jpeg conversion failed: x",
            frozenset({ImportFailureStage.JPEG}),
        )

        assert failure_reason(failure, tmp_path) == "jpeg conversion failed: x"

    def test_batch_failures_words_a_refusal(self, tmp_path: Path) -> None:
        failure = AlbumFailure(
            tmp_path / "A",
            reason="",
            error=EmptyImageCaptureDirError(tmp_path / "ic"),
        )

        assert "Could not find any image capture files in ic" in batch_failures(
            [failure],
            tmp_path,
        )
