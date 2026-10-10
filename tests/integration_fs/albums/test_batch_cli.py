"""CLI behavior of the ``albums`` batch commands."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from photree.album.id import format_album_external_id, generate_album_id
from photree.album.importer.batch import AlbumFailure, ImportFailureStage
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.batchcli.check import run_batch_check
from photree.albums.cli.import_cmd import retry_commands
from photree.albums.cmd_handler import AlbumStepError, run_album_step
from photree.albums.cmd_handler.stats import batch_stats
from photree.cli import app

runner = CliRunner()


def _album(base: Path, name: str) -> tuple[Path, str]:
    album = base / name
    image = album / "ios-main" / "orig-img" / "IMG_0001.HEIC"
    image.parent.mkdir(parents=True)
    image.write_text("data", encoding="utf-8")
    album_id = generate_album_id()
    save_album_metadata(album, AlbumMetadata(id=album_id))
    return album, album_id


class TestList:
    def test_invalid_format_is_rejected(self, tmp_path: Path) -> None:
        # Regression: an unknown --format silently produced text.
        _album(tmp_path, "2024-07-14 - Hiking")

        result = runner.invoke(
            app, ["albums", "list", "-d", str(tmp_path), "--format", "json"]
        )

        assert result.exit_code == 2

    def test_text_output_honors_output_file(self, tmp_path: Path) -> None:
        # Regression: -o was ignored in text mode.
        albums_dir = tmp_path / "albums"
        _, album_id = _album(albums_dir, "2024-07-14 - Hiking")
        out = tmp_path / "out.txt"

        result = runner.invoke(
            app, ["albums", "list", "-d", str(albums_dir), "-o", str(out)]
        )

        assert result.exit_code == 0, result.output
        text = out.read_text(encoding="utf-8")
        assert "2024-07-14 - Hiking" in text
        assert format_album_external_id(album_id) in text
        assert "Hiking" not in result.output

    def test_csv_output_file(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        _album(albums_dir, "2024-07-14 - Hiking")
        out = tmp_path / "out.csv"

        result = runner.invoke(
            app,
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

        result = runner.invoke(app, ["albums", "list", "-a", str(album)])

        assert result.exit_code == 1
        assert "Albums with missing IDs found" in result.output
        assert "photree albums fix --id --album-dir" in result.output

    def test_list_media_invalid_format_is_rejected(self, tmp_path: Path) -> None:
        _album(tmp_path, "2024-07-14 - Hiking")

        result = runner.invoke(
            app, ["albums", "list-media", "-d", str(tmp_path), "--format", "xml"]
        )

        assert result.exit_code == 2


class TestRunBatchCheck:
    def test_failures_counted_once_and_no_exit(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        # Two albums colliding on the same date (cross-album failure) that are
        # also structurally incomplete (per-album failure). Regression: they
        # were counted twice and ``passed`` was never decremented.
        a, _ = _album(tmp_path, "2024-07-14 - Hiking")
        b, _ = _album(tmp_path, "2024-07-14 - Dinner")

        passed = run_batch_check(
            [a, b],
            tmp_path,
            checksum=False,
            check_exif_date_match=False,
            exit_on_failure=False,
        )

        assert passed is False

    def test_exit_on_failure_raises(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        a, _ = _album(tmp_path, "2024-07-14 - Hiking")
        b, _ = _album(tmp_path, "2024-07-14 - Dinner")

        with pytest.raises(typer.Exit) as exc_info:
            run_batch_check(
                [a, b], tmp_path, checksum=False, check_exif_date_match=False
            )

        assert exc_info.value.exit_code == 1

    def test_no_albums_returns_true_without_exit(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        assert (
            run_batch_check(
                [], tmp_path, check_exif_date_match=False, exit_on_failure=False
            )
            is True
        )

    def test_summary_counts(self, tmp_path: Path, stub_sips_on_path: Path) -> None:
        _album(tmp_path, "2024-07-14 - Hiking")
        _album(tmp_path, "2024-07-14 - Dinner")

        result = runner.invoke(
            app,
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
            raise OSError("disk on fire")

        ends: list[tuple[str, bool, tuple[str, ...]]] = []
        outcome = run_album_step(
            tmp_path, boom, name="a", on_end=lambda *args: ends.append(args)
        )

        assert outcome.failure is not None
        assert outcome.failure.reason == "disk on fire"
        assert ends == [("a", False, ("disk on fire",))]

    def test_step_error_keeps_labels(self, tmp_path: Path) -> None:
        def soft_fail() -> None:
            raise AlbumStepError("2 files failed", ("x", "y"))

        ends: list[tuple[str, bool, tuple[str, ...]]] = []
        outcome = run_album_step(
            tmp_path, soft_fail, name="a", on_end=lambda *args: ends.append(args)
        )

        assert outcome.failure is not None
        assert outcome.failure.reason == "2 files failed"
        assert ends == [("a", False, ("x", "y"))]


class TestBatchStats:
    def test_one_bad_album_does_not_abort(self, tmp_path: Path) -> None:
        # Regression: one unreadable album crashed the whole stats run.
        good, _ = _album(tmp_path, "2024-07-14 - Hiking")
        bad = tmp_path / "not-an-album"
        bad.mkdir()

        result = batch_stats([good, bad])

        assert [f.album_dir for f in result.failures] == [bad]
        assert result.stats is not None


class TestImportCheck:
    def test_reports_reason_per_album(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        albums_dir = tmp_path / "albums"
        (albums_dir / "2024-07-14 - Hiking").mkdir(parents=True)
        source = tmp_path / "ic"
        source.mkdir()
        (source / "IMG_0001.HEIC").write_text("x", encoding="utf-8")

        result = runner.invoke(
            app,
            ["albums", "import-check", "-d", str(albums_dir), "-s", str(source)],
        )

        assert result.exit_code == 1
        assert "0 album(s) ready to import, 1 not ready." in result.output
        assert "no to-import-* staging entries" in result.output
        assert "photree album import-check --album-dir" in result.output


class TestBatchImportRetryCommands:
    def test_failed_import_is_retried_with_import(self, tmp_path: Path) -> None:
        failure = AlbumFailure(tmp_path / "A", "copy failed")

        assert retry_commands(failure, tmp_path) == [
            'photree album import --album-dir "A"'
        ]

    def test_partial_failure_is_not_retried_with_import(self, tmp_path: Path) -> None:
        # The staging was consumed by the completed import, so 'album import'
        # would only report that there is nothing to import.
        failure = AlbumFailure(
            tmp_path / "A",
            "jpeg conversion failed: ...; face detection failed: ...",
            frozenset({ImportFailureStage.JPEG, ImportFailureStage.FACES}),
        )

        assert retry_commands(failure, tmp_path) == [
            'photree album refresh --refresh-jpeg --album-dir "A"',
            'photree album detect-faces --album-dir "A"',
        ]
