"""Tests for photree.cli package."""

from typer.testing import CliRunner

from photree.cli import app

runner = CliRunner()


class TestVersionCommand:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert result.output.strip()

    def test_short_version_flag(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert "photree" in result.output.lower()
