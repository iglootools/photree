import shutil
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest

from photree.album.exif import TIMESTAMP_TAGS
from photree.common.exif import read_exif_timestamps, set_exif_date_time
from tests.fakes import invoke_cli

requires_exiftool = pytest.mark.skipif(
    not shutil.which("exiftool"),
    reason="exiftool not installed",
)


def _jpeg(path: Path) -> Path:
    cv2.imwrite(str(path), np.zeros((8, 8, 3), dtype=np.uint8))
    return path


class TestFlagSelection:
    def test_no_flag(self, tmp_path: Path) -> None:
        result = invoke_cli(["album", "fix-exif", str(tmp_path / "a.jpg")])
        assert result.exit_code == 2
        assert "Specify exactly one" in result.output

    def test_two_flags(self) -> None:
        result = invoke_cli(
            ["album", "fix-exif", "--shift-date", "1", "--shift-time", "2", "x.jpg"],
        )
        assert result.exit_code == 2
        assert "mutually exclusive" in result.output

    @pytest.mark.parametrize(
        "value",
        ["2024-07", "2024-02-30", "2024-13-45", "24-7-20"],
    )
    def test_impossible_date_is_a_usage_error(self, value: str) -> None:
        result = invoke_cli(["album", "fix-exif", "--set-date", value, "x.jpg"])
        assert result.exit_code == 2
        assert "YYYY-MM-DD" in result.output

    @pytest.mark.parametrize(
        "value",
        ["2024-02-30T10:00:00", "2024-07-20T25:00:00", "yesterday", "2024-07-20"],
    )
    def test_impossible_or_date_only_timestamp_is_a_usage_error(
        self,
        value: str,
    ) -> None:
        result = invoke_cli(["album", "fix-exif", "--set-date-time", value, "x.jpg"])
        assert result.exit_code == 2
        assert "Invalid timestamp" in result.output


@requires_exiftool
class TestExecution:
    def test_success_prints_check_after_work(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")
        result = invoke_cli(
            ["album", "fix-exif", "--set-date-time", "2024-07-20T13:55:20", str(img)],
        )
        assert result.exit_code == 0, result.output
        assert "✓ fix-exif" in result.output
        assert "Done. 1 file(s) updated." in result.output

    def test_failure_exits_1_without_check_line(self, tmp_path: Path) -> None:
        """Regression: ✓ was printed before the work and exit code was 0."""
        not_media = tmp_path / "notes.txt"
        not_media.write_text("hello", encoding="utf-8")
        result = invoke_cli(["album", "fix-exif", "--shift-time", "-2", str(not_media)])
        assert result.exit_code == 1
        assert "✓ fix-exif" not in result.output
        assert "fix-exif failed" in result.output
        assert "notes.txt" in result.output


def _dated_jpeg(path: Path, timestamp: str = "2024-07-20T13:55:20") -> Path:
    img = _jpeg(path)
    set_exif_date_time([img], timestamp)
    return img


def _date_of(path: Path) -> datetime | None:
    [ts] = read_exif_timestamps([path], TIMESTAMP_TAGS) or [None]
    return ts


@requires_exiftool
class TestDryRun:
    @pytest.mark.parametrize(
        ("option", "value", "new_value"),
        [
            ("--set-date", "2023-01-02", "2023:01:02 13:55:20"),
            ("--set-date-time", "2023-01-02T03:04:05", "2023:01:02 03:04:05"),
            ("--shift-date", "-1", "2024:07:19 13:55:20"),
            ("--shift-time", "-6", "2024:07:20 07:55:20"),
        ],
    )
    def test_dry_run_lists_changes_without_writing(
        self,
        tmp_path: Path,
        option: str,
        value: str,
        new_value: str,
    ) -> None:
        img = _dated_jpeg(tmp_path / "a.jpg")

        result = invoke_cli(["album", "fix-exif", "--dry-run", option, value, str(img)])

        assert result.exit_code == 0, result.output
        assert (
            f"[dry-run] Would fix-exif {img}: 2024:07:20 13:55:20 -> {new_value}"
            in (result.output)
        )
        assert "[dry-run] 1 file(s) would be updated." in result.output
        assert _date_of(img) == datetime(2024, 7, 20, 13, 55, 20)

    def test_dry_run_shows_a_file_without_a_date(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")

        result = invoke_cli(
            [
                "album",
                "fix-exif",
                "-n",
                "--set-date-time",
                "2023-01-02T03:04:05",
                str(img),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "(no date) -> 2023:01:02 03:04:05" in result.output
        assert _date_of(img) is None


@requires_exiftool
class TestReport:
    def test_shift_reports_old_and_new_dates(self, tmp_path: Path) -> None:
        img = _dated_jpeg(tmp_path / "a.jpg")

        result = invoke_cli(["album", "fix-exif", "--shift-time", "3", str(img)])

        assert result.exit_code == 0, result.output
        assert "2024:07:20 13:55:20 -> 2024:07:20 16:55:20" in result.output
        assert _date_of(img) == datetime(2024, 7, 20, 16, 55, 20)
