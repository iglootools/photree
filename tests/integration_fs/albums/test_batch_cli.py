from pathlib import Path

import pytest
import typer

from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.id import format_album_external_id
from photree.album.jpeg import JpegConversionFailure
from photree.album.refresh import refresh_album_derived_data
from photree.albums.batchcli.check import run_batch_check
from photree.albums.cli.import_cmd import retry_commands
from photree.albums.cmd_handler import AlbumStepError, run_album_step
from photree.albums.cmd_handler.importer import AlbumFailure, ImportFailureStage
from photree.albums.cmd_handler.stats import batch_stats
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from tests.fakes import ALL_DEPS_WHICH, copy_convert_single, invoke_cli
from tests.testkit import make_album, make_gallery, make_gallery_album


def _gallery_album(parent: Path, name: str, link_mode: LinkMode) -> Path:
    """Return an album of a *link_mode* gallery, refreshed so it passes a check."""
    gallery = make_gallery(parent, link_mode=link_mode)
    album, _ = make_gallery_album(gallery, name)
    refresh_album_derived_data(
        album,
        link_mode=link_mode,
        convert_file=copy_convert_single,
    )
    return album


class TestList:
    def test_invalid_format_is_rejected(self, tmp_path: Path) -> None:
        # Regression: an unknown --format silently produced text.
        make_album(tmp_path, "2024-07-14 - Hiking")

        result = invoke_cli(["albums", "list", "-d", str(tmp_path), "--format", "json"])

        assert result.exit_code == 2

    def test_text_output_honors_output_file(self, tmp_path: Path) -> None:
        # Regression: -o was ignored in text mode.
        albums_dir = tmp_path / "albums"
        _, album_id = make_album(albums_dir, "2024-07-14 - Hiking")
        out = tmp_path / "out.txt"

        result = invoke_cli(["albums", "list", "-d", str(albums_dir), "-o", str(out)])

        assert result.exit_code == 0, result.output
        text = out.read_text(encoding="utf-8")
        assert "2024-07-14 - Hiking" in text
        assert format_album_external_id(album_id) in text
        assert "Hiking" not in result.output

    def test_csv_output_file(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        make_album(albums_dir, "2024-07-14 - Hiking")
        out = tmp_path / "out.csv"

        result = invoke_cli(
            [
                "albums",
                "list",
                "-d",
                str(albums_dir),
                "--format",
                "csv",
                "-o",
                str(out),
            ],
        )

        assert result.exit_code == 0, result.output
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("id,path,date")
        assert len(lines) == 2

    def test_missing_id_suggests_albums_fix(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        (album / "ios-main" / "orig-img").mkdir(parents=True)

        result = invoke_cli(["albums", "list", "-a", str(album)])

        assert result.exit_code == 1
        assert "Albums with missing IDs found" in result.output
        assert "photree albums fix --id --album-dir" in result.output

    def test_list_media_invalid_format_is_rejected(self, tmp_path: Path) -> None:
        make_album(tmp_path, "2024-07-14 - Hiking")

        result = invoke_cli(
            ["albums", "list-media", "-d", str(tmp_path), "--format", "xml"],
        )

        assert result.exit_code == 2


class TestRunBatchCheck:
    def test_failures_counted_once_and_no_exit(self, tmp_path: Path) -> None:
        # Two albums colliding on the same date (cross-album failure) that are
        # also structurally incomplete (per-album failure). Regression: they
        # were counted twice and ``passed`` was never decremented.
        a, _ = make_album(tmp_path, "2024-07-14 - Hiking")
        b, _ = make_album(tmp_path, "2024-07-14 - Dinner")

        passed = run_batch_check(
            [a, b],
            tmp_path,
            which=ALL_DEPS_WHICH,
            cwd=tmp_path,
            checksum=False,
            check_exif_date_match=False,
            exit_on_failure=False,
        )

        assert passed is False

    def test_exit_on_failure_raises(self, tmp_path: Path) -> None:
        a, _ = make_album(tmp_path, "2024-07-14 - Hiking")
        b, _ = make_album(tmp_path, "2024-07-14 - Dinner")

        with pytest.raises(typer.Exit) as exc_info:
            run_batch_check(
                [a, b],
                tmp_path,
                which=ALL_DEPS_WHICH,
                cwd=tmp_path,
                checksum=False,
                check_exif_date_match=False,
            )

        assert exc_info.value.exit_code == 1

    def test_each_album_is_checked_against_its_gallery_link_mode(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: every album was checked against the first one's link mode."""
        hardlinked = _gallery_album(
            tmp_path / "a",
            "2024-07-14 - Hiking",
            LinkMode.HARDLINK,
        )
        copied = _gallery_album(tmp_path / "b", "2024-07-15 - Beach", LinkMode.COPY)

        passed = run_batch_check(
            [hardlinked, copied],
            tmp_path,
            which=ALL_DEPS_WHICH,
            cwd=tmp_path,
            check_exif_date_match=False,
            exit_on_failure=False,
        )

        assert passed is True

    def test_unreadable_gallery_yaml_fails_only_its_album(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: a corrupt gallery.yaml next to the first album aborted all."""
        broken = _gallery_album(tmp_path / "a", "2024-07-14 - Hiking", LinkMode.COPY)
        (tmp_path / "a" / "gallery" / PHOTREE_DIR / "gallery.yaml").write_text(
            "link_mode: [",
            encoding="utf-8",
        )
        healthy = _gallery_album(tmp_path / "b", "2024-07-15 - Beach", LinkMode.COPY)

        result = invoke_cli(["albums", "check", "-a", str(broken), "-a", str(healthy)])

        assert result.exit_code == 1
        assert "1 album(s) passed, 1 with warnings, 1 failed." in result.output

    def test_corrupt_album_yaml_fails_its_album_and_keeps_the_summary(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the cross-album scans raised, losing the summary."""
        corrupt, _ = make_album(tmp_path, "2024-07-14 - Hiking")
        (corrupt / ".photree" / "album.yaml").write_text("id: [", encoding="utf-8")
        make_album(tmp_path, "2024-07-15 - Beach")

        result = invoke_cli(["albums", "check", "-d", str(tmp_path), "--no-checksum"])

        assert result.exit_code == 1
        assert "Cross-album checks:" in result.output
        assert "Done." in result.output
        investigate = result.output.split("To investigate failures:")[1]
        assert "2024-07-14 - Hiking" in investigate
        assert "--no-checksum" in investigate, "the retry reproduces the run"

    def test_no_albums_returns_true_without_exit(self, tmp_path: Path) -> None:
        assert (
            run_batch_check(
                [],
                tmp_path,
                which=ALL_DEPS_WHICH,
                cwd=tmp_path,
                check_exif_date_match=False,
                exit_on_failure=False,
            )
            is True
        )

    def test_summary_counts(self, tmp_path: Path) -> None:
        make_album(tmp_path, "2024-07-14 - Hiking")
        make_album(tmp_path, "2024-07-14 - Dinner")

        result = invoke_cli(
            [
                "albums",
                "check",
                "-d",
                str(tmp_path),
                "--no-checksum",
                "--no-check-exif-date-match",
            ],
        )

        assert result.exit_code == 1
        assert "0 album(s) passed" in result.output
        assert "2 failed" in result.output


class TestRunAlbumStep:
    def test_exception_becomes_failure(self, tmp_path: Path) -> None:
        def boom() -> None:
            message = "disk on fire"
            raise OSError(message)

        ends: list[tuple[str, bool, tuple[str, ...]]] = []

        def record_end(
            album: str,
            *,
            success: bool,
            error_labels: tuple[str, ...],
        ) -> None:
            ends.append((album, success, error_labels))

        outcome = run_album_step(
            tmp_path,
            boom,
            name="a",
            on_end=record_end,
        )

        assert outcome.failure is not None
        assert outcome.failure.reason == "disk on fire"
        assert ends == [("a", False, ("disk on fire",))]

    def test_step_error_keeps_labels(self, tmp_path: Path) -> None:
        def soft_fail() -> None:
            message = "2 files failed"
            raise AlbumStepError(message, ("x", "y"))

        ends: list[tuple[str, bool, tuple[str, ...]]] = []

        def record_end(
            album: str,
            *,
            success: bool,
            error_labels: tuple[str, ...],
        ) -> None:
            ends.append((album, success, error_labels))

        outcome = run_album_step(
            tmp_path,
            soft_fail,
            name="a",
            on_end=record_end,
        )

        assert outcome.failure is not None
        assert outcome.failure.reason == "2 files failed"
        assert ends == [("a", False, ("x", "y"))]


class TestBatchStats:
    def test_one_bad_album_does_not_abort(self, tmp_path: Path) -> None:
        # Regression: one unreadable album crashed the whole stats run.
        good, _ = make_album(tmp_path, "2024-07-14 - Hiking")
        bad = tmp_path / "not-an-album"
        bad.mkdir()

        result = batch_stats([good, bad])

        assert [f.album_dir for f in result.failures] == [bad]
        assert result.stats is not None


def _image_capture_dir(tmp_path: Path) -> Path:
    source = tmp_path / "ic"
    source.mkdir()
    (source / "IMG_0001.HEIC").write_text("x", encoding="utf-8")
    return source


class TestImportCheck:
    def test_reports_reason_per_album(self, tmp_path: Path) -> None:
        album = tmp_path / "albums" / "2024-07-14 - Hiking"
        album.mkdir(parents=True)
        source = _image_capture_dir(tmp_path)

        result = invoke_cli(
            ["albums", "import-check", "-a", str(album), "-s", str(source)],
        )

        assert result.exit_code == 1
        assert "0 album(s) ready to import, 1 not ready." in result.output
        assert "no to-import-* staging entries" in result.output
        assert "photree album import-check --album-dir" in result.output

    def test_scan_skips_directories_the_import_would_skip(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: hidden and unstaged directories failed the check."""
        albums_dir = tmp_path / "albums"
        (albums_dir / ".hidden").mkdir(parents=True)
        (albums_dir / "notes").mkdir()
        for name in ("2024-07-14 - Hiking", "2024-07-15 - Biking"):
            (albums_dir / name / "to-import-ios-main").mkdir(parents=True)
        source = _image_capture_dir(tmp_path)

        result = invoke_cli(
            ["albums", "import-check", "-d", str(albums_dir), "-s", str(source)],
        )

        assert "Skipped 2 directory(ies) without a to-import-* staging" in (
            result.output
        )
        assert "Import Tasks (2 album(s)):" in result.output


class TestBatchImportRetryCommands:
    def test_failed_import_is_retried_with_import(self, tmp_path: Path) -> None:
        failure = AlbumFailure(tmp_path / "A", error=OSError("copy failed"))

        assert retry_commands(failure, tmp_path) == [
            'photree album import --album-dir "A"',
        ]

    def test_partial_failure_is_not_retried_with_import(self, tmp_path: Path) -> None:
        # The staging was consumed by the completed import, so 'album import'
        # would only report that there is nothing to import.
        failure = AlbumFailure(
            tmp_path / "A",
            jpeg_failures=(("main", JpegConversionFailure("IMG_0001.HEIC", "bad")),),
            face_failures=(
                ("main", FaceFailure("0001", FaceFailureStage.DETECTION, "boom")),
            ),
        )

        assert failure.stages == {ImportFailureStage.JPEG, ImportFailureStage.FACES}

        assert retry_commands(failure, tmp_path) == [
            'photree album refresh --refresh-jpeg --album-dir "A"',
            'photree album detect-faces --album-dir "A"',
        ]
