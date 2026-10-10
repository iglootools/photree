"""CLI tests for ``photree album fix-exif``."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.cli import app

runner = CliRunner()

requires_exiftool = pytest.mark.skipif(
    not shutil.which("exiftool"), reason="exiftool not installed"
)


def _jpeg(path: Path) -> Path:
    import cv2
    import numpy as np

    cv2.imwrite(str(path), np.zeros((8, 8, 3), dtype=np.uint8))
    return path


class TestFlagSelection:
    def test_no_flag(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["album", "fix-exif", str(tmp_path / "a.jpg")])
        assert result.exit_code == 1
        assert "Specify exactly one" in result.output

    def test_two_flags(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["album", "fix-exif", "--shift-date", "1", "--shift-time", "2", "x.jpg"],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_invalid_date(self) -> None:
        result = runner.invoke(
            app, ["album", "fix-exif", "--set-date", "2024-07", "x.jpg"]
        )
        assert result.exit_code == 1
        assert "expected YYYY-MM-DD" in result.output


@requires_exiftool
class TestExecution:
    def test_success_prints_check_after_work(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")
        result = runner.invoke(
            app,
            ["album", "fix-exif", "--set-date-time", "2024-07-20T13:55:20", str(img)],
        )
        assert result.exit_code == 0, result.output
        assert "✓ fix-exif" in result.output
        assert "Done. 1 file(s) updated." in result.output

    def test_failure_exits_1_without_check_line(self, tmp_path: Path) -> None:
        """Regression: ✓ was printed before the work and exit code was 0."""
        not_media = tmp_path / "notes.txt"
        not_media.write_text("hello", encoding="utf-8")
        result = runner.invoke(
            app, ["album", "fix-exif", "--shift-time", "-2", str(not_media)]
        )
        assert result.exit_code == 1
        assert "✓ fix-exif" not in result.output
        assert "fix-exif failed" in result.output
        assert "notes.txt" in result.output
