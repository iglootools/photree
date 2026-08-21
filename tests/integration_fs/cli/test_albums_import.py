"""CLI tests for ``albums import`` failure reporting.

A per-album failure used to be counted as a "skip" and its reason discarded,
so a run where every album failed printed a success-shaped summary and exited
0. These cover the reason reaching the user and the exit code reflecting it.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.album.store.protocol import ios_import_dir
from photree.cli import app

runner = CliRunner()

SEL_DIR = ios_import_dir("main")


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _image_capture_dir(tmp_path: Path) -> Path:
    ic_dir = tmp_path / "image_capture"
    for name in ("IMG_0001.HEIC", "IMG_0001.AAE"):
        _write(ic_dir / name)
    return ic_dir


def _staged_album(parent: Path, name: str) -> Path:
    album = parent / name
    _write(album / SEL_DIR / "IMG_0001.HEIC")
    return album


def _invoke(albums_dir: Path, ic_dir: Path):
    return runner.invoke(
        app,
        [
            "albums",
            "import",
            "-d",
            str(albums_dir),
            "-s",
            str(ic_dir),
            "--skip-heic-to-jpeg",
        ],
    )


class TestFailureReporting:
    def test_failure_reason_is_printed_and_exit_code_is_nonzero(
        self, tmp_path: Path
    ) -> None:
        ic_dir = _image_capture_dir(tmp_path)
        albums_dir = tmp_path / "albums"
        album = _staged_album(albums_dir, "2024-07-14 - Hiking")
        # A regular file where the archive directory must be created makes the
        # import of this one album fail without aborting the batch.
        _write(album / "ios-main")

        result = _invoke(albums_dir, ic_dir)

        assert result.exit_code == 1
        assert "1 failed" in result.output
        assert "Failed albums:" in result.output
        assert "2024-07-14 - Hiking" in result.output
        assert "Not a directory" in result.output
        assert "photree album import --album-dir" in result.output

    def test_failures_are_not_counted_as_skips(self, tmp_path: Path) -> None:
        ic_dir = _image_capture_dir(tmp_path)
        albums_dir = tmp_path / "albums"
        _write(_staged_album(albums_dir, "2024-07-14 - Hiking") / "ios-main")
        # An album with no staging entry at all: that one is a genuine skip.
        (albums_dir / "2024-07-15 - Rest").mkdir()

        result = _invoke(albums_dir, ic_dir)

        assert "0 album(s) imported, 1 failed, 1 skipped." in result.output

    def test_all_succeeding_exits_zero(self, tmp_path: Path) -> None:
        ic_dir = _image_capture_dir(tmp_path)
        albums_dir = tmp_path / "albums"
        album = _staged_album(albums_dir, "2024-07-14 - Hiking")

        result = _invoke(albums_dir, ic_dir)

        assert result.exit_code == 0
        assert "0 failed" in result.output
        assert (album / "ios-main" / "orig-img" / "IMG_0001.HEIC").exists()
