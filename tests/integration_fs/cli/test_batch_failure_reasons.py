"""Every batch command must say *why* an item failed, not just that it did.

A batch that reports only which albums failed forces a per-album re-run to
learn anything the batch already knew. These pin the reason to the output.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _album(base: Path, name: str) -> Path:
    album = base / name
    _write(album / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    return album


class TestBatchInit:
    def test_reason_is_printed_for_an_already_initialized_album(
        self, tmp_path: Path
    ) -> None:
        _album(tmp_path, "2024-07-14 - Hiking")

        result = runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])

        assert result.exit_code == 1
        assert "Failed albums:" in result.output
        assert "already initialized" in result.output
        assert "To investigate failures:" in result.output


class TestBatchRefresh:
    def test_jpeg_failure_reason_reaches_the_summary(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        # A .HEIC whose bytes are not HEIC: sips rejects it on macOS, and the
        # stub exits non-zero everywhere else.
        album = tmp_path / "2024-07-14 - Hiking"
        _write(album / "ios-main" / "orig-img" / "IMG_0001.HEIC", "not heic")
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))

        result = runner.invoke(app, ["albums", "refresh", "-d", str(tmp_path)])

        assert result.exit_code == 1
        assert "Failed albums:" in result.output
        assert "IMG_0001" in result.output
        assert "0 album(s) refreshed, 1 failed" in result.output


class TestBatchFailureReport:
    """The shared formatter pairs each album with its reason."""

    def test_formats_path_and_reason(self, tmp_path: Path) -> None:
        from photree.albums.cli.batch_ops import batch_failures_report
        from photree.albums.cmd_handler import BatchFailure

        report = batch_failures_report(
            [BatchFailure(album_dir=tmp_path / "a", reason="disk on fire")], tmp_path
        )

        assert "a" in report
        assert "disk on fire" in report


@pytest.mark.parametrize(
    "handler_module",
    [
        "photree.albums.cmd_handler.init",
        "photree.albums.cmd_handler.refresh",
        "photree.albums.cmd_handler.fix",
        "photree.albums.cmd_handler.fix_ios",
    ],
)
def test_every_handler_result_exposes_failures(handler_module: str) -> None:
    """Guard against a handler regressing to a bare list of paths."""
    import importlib

    module = importlib.import_module(handler_module)
    result_cls = next(
        obj
        for name, obj in vars(module).items()
        if name.startswith("Batch") and name.endswith("Result")
    )
    assert "failures" in result_cls.__dataclass_fields__
    assert "failed_albums" not in result_cls.__dataclass_fields__, (
        "failed_albums must be derived from failures, not stored alongside it"
    )
