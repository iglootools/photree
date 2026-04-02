"""Tests for photree.cli package."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from typer.testing import CliRunner

from photree.cli import app
from photree.album.store.fs import save_album_metadata
from photree.album.store.protocol import (
    AlbumMetadata,
    format_album_external_id,
    generate_album_id,
)

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_media_source(album_dir: Path) -> None:
    """Create a minimal iOS media source so the album is detected."""
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


def _setup_album(
    base_dir: Path, name: str, album_id: str | None = None
) -> tuple[Path, str]:
    """Create a complete album directory. Returns (path, album_id)."""
    album_dir = base_dir / name
    _setup_media_source(album_dir)
    aid = album_id if album_id is not None else generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return (album_dir, aid)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a list of dicts as a CSV file."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buf.getvalue())


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


# ---------------------------------------------------------------------------
# albums rename-from-csv
# ---------------------------------------------------------------------------


class TestAlbumsRenameFromCsv:
    def test_rename_title(self, tmp_path: Path) -> None:
        _, aid = _setup_album(tmp_path, "2024-06-15 - Old Title")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "New Title",
                    "location": "",
                },
            ],
        )
        result = runner.invoke(
            app,
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Renamed 1 album(s)" in result.output
        assert (tmp_path / "2024-06-15 - New Title").is_dir()
        assert not (tmp_path / "2024-06-15 - Old Title").exists()

    def test_dry_run(self, tmp_path: Path) -> None:
        _, aid = _setup_album(tmp_path, "2024-06-15 - Trip")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "New Trip",
                    "location": "",
                },
            ],
        )
        result = runner.invoke(
            app,
            [
                "albums",
                "rename-from-csv",
                str(csv_file),
                "-d",
                str(tmp_path),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        # Original directory is unchanged
        assert (tmp_path / "2024-06-15 - Trip").is_dir()

    def test_no_changes(self, tmp_path: Path) -> None:
        _, aid = _setup_album(tmp_path, "2024-06-15 - Trip")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "Trip",
                    "location": "",
                },
            ],
        )
        result = runner.invoke(
            app,
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Nothing to rename" in result.output

    def test_empty_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("id,series,title,location\n")
        result = runner.invoke(
            app,
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_album_dir_option(self, tmp_path: Path) -> None:
        album_dir, aid = _setup_album(tmp_path, "2024-06-15 - Old")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "New",
                    "location": "",
                },
            ],
        )
        result = runner.invoke(
            app,
            [
                "albums",
                "rename-from-csv",
                str(csv_file),
                "-a",
                str(album_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Renamed 1 album(s)" in result.output

    def test_missing_album_id_exits(self, tmp_path: Path) -> None:
        # Album with empty album.yaml (no valid ID)
        album_dir = tmp_path / "2024-06-15 - Broken"
        _setup_media_source(album_dir)
        photree_dir = album_dir / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        csv_file = tmp_path / "rename.csv"
        csv_file.write_text("id,series,title,location\nalbum_x,,,New\n")
        result = runner.invoke(
            app,
            ["albums", "rename-from-csv", str(csv_file), "-a", str(album_dir)],
        )
        assert result.exit_code == 1
        assert (
            "missing IDs" in result.output.lower()
            or "missing ids" in result.output.lower()
        )
