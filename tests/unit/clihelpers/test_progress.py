"""Tests for photree.clihelpers.progress result lines."""

import pytest

from photree.clihelpers.progress import BatchProgressBar, StageProgressBar


class TestResultLinesWithoutOnStart:
    """Regression: on_end without a prior on_start silently dropped the line."""

    def test_batch_on_end(self, capsys: pytest.CaptureFixture[str]) -> None:
        with BatchProgressBar(
            total=1, description="Checking", done_description="check"
        ) as bar:
            bar.on_end("2024-07-14 - Trip", success=False, error_labels=("ids",))
        out = capsys.readouterr().out
        assert "check 2024-07-14 - Trip" in out
        assert "| ids" in out

    def test_stage_on_end(self, capsys: pytest.CaptureFixture[str]) -> None:
        with StageProgressBar(total=1) as bar:
            bar.on_end("refresh")
        assert "refresh" in capsys.readouterr().out


class TestBatchSuffix:
    def test_errors_and_warnings_both_rendered(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with BatchProgressBar(
            total=1, description="Checking", done_description="check"
        ) as bar:
            bar.on_start("a")
            bar.on_end("a", success=True, warning_labels=("exif",))
        assert "check a | exif" in capsys.readouterr().out
