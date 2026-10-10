"""User text must survive Rich markup.

Rich parses ``[...]`` as a markup tag and silently drops the ones it does not
recognize, so an album named ``2024-07-14 - Hiking [private]`` used to print
as ``2024-07-14 - Hiking `` wherever its name was interpolated next to
intentional markup (``✓``/``✗`` icons, colors). These pin the bracketed text
to representative outputs of each command family.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from rich.markup import render
from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.clihelpers.progress import (
    BatchProgressBar,
    FileProgressBar,
    StageProgressBar,
)
from photree.collection.stats.models import CollectionStatsEntry, GalleryCollectionStats
from photree.collection.stats.output import format_collections_table
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionStrategy,
)
from photree.common.formatting import CHECK, markup_escape
from photree.fsprotocol import GalleryMetadata, LinkMode, save_gallery_metadata

runner = CliRunner()

PRIVATE_ALBUM = "2024-07-14 - Hiking [private]"


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _album(base: Path, name: str, *, with_id: bool = True) -> Path:
    album = base / name
    _write(album / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    if with_id:
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    return album


def _gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(
        gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK, faces_enabled=False)
    )
    return gallery


class TestMarkupEscape:
    def test_round_trips_through_rich_markup(self) -> None:
        assert render(f"{CHECK} {markup_escape(PRIVATE_ALBUM)}").plain == (
            f"✓ {PRIVATE_ALBUM}"
        )

    def test_accepts_paths(self) -> None:
        assert render(markup_escape(Path("a [b]"))).plain == "a [b]"


class TestProgressBars:
    def test_batch_result_line_keeps_brackets(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with BatchProgressBar(
            total=1, description="Checking", done_description="check"
        ) as bar:
            bar.on_start(PRIVATE_ALBUM)
            bar.on_end(
                PRIVATE_ALBUM,
                success=False,
                error_labels=("[ios:main] bad file",),
                warning_labels=("[x] warn",),
            )
        out = capsys.readouterr().out
        assert f"check {PRIVATE_ALBUM}" in out
        assert "| [ios:main] bad file" in out
        assert "| [x] warn" in out

    def test_batch_skipped_line_keeps_brackets(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with BatchProgressBar(
            total=1, description="Importing", done_description="import"
        ) as bar:
            bar.on_skipped(PRIVATE_ALBUM, "nothing in [staging]", warn=True)
        assert f"{PRIVATE_ALBUM} (nothing in [staging])" in capsys.readouterr().out

    def test_file_and_stage_lines_keep_brackets(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with FileProgressBar(
            total=1, description="Checking", done_description="check"
        ) as bar:
            bar.on_end("IMG [1].jpg", success=True)
        with StageProgressBar(total=1) as stage_bar:
            stage_bar.on_end("[main] import")
        out = capsys.readouterr().out
        assert "check IMG [1].jpg" in out
        assert "[main] import" in out


class TestAlbumsBatchFailures:
    def test_failed_album_listing_keeps_private_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _album(tmp_path, PRIVATE_ALBUM)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])

        assert result.exit_code == 1
        assert "Failed albums:" in result.output
        # Progress result line, failure listing, and retry command.
        assert result.output.count(PRIVATE_ALBUM) >= 3
        assert f'--album-dir "{PRIVATE_ALBUM}"' in result.output


class TestAlbumCheck:
    def test_preflight_and_troubleshoot_keep_brackets(
        self, tmp_path: Path, stub_sips_on_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album = _album(tmp_path, PRIVATE_ALBUM)
        # A second media source makes every media line carry a "[name] " prefix.
        _write(album / "std-nelu" / "orig-img" / "DSC_0001.JPG")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            [
                "album",
                "check",
                "-a",
                str(album),
                "--no-check-exif-date-match",
                "--no-checksum",
            ],
        )

        assert result.exit_code == 1
        assert "[main] main-img" in result.output
        assert "[nelu] nelu-jpg" in result.output
        # Troubleshooting suggestions quote the album dir verbatim.
        assert f'--album-dir "{PRIVATE_ALBUM}"' in result.output


class TestGalleryImport:
    def test_naming_error_keeps_bracketed_tag(self, tmp_path: Path) -> None:
        gallery = _gallery(tmp_path)
        source = _album(tmp_path / "src", "2024-07-14 - Hiking [secret]")

        result = runner.invoke(
            app, ["gallery", "import", "-a", str(source), "-g", str(gallery)]
        )

        assert result.exit_code == 1
        assert "2024-07-14 - Hiking [secret] — naming:" in result.output

    def test_skipped_listing_keeps_private_tag(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        gallery = _gallery(tmp_path)
        album_id = generate_album_id()
        target = gallery / "albums" / "2024" / PRIVATE_ALBUM
        _write(target / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        save_album_metadata(target, AlbumMetadata(id=album_id))
        source = tmp_path / "src" / PRIVATE_ALBUM
        _write(source / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        save_album_metadata(source, AlbumMetadata(id=album_id))

        result = runner.invoke(
            app, ["gallery", "import", "-a", str(source), "-g", str(gallery)]
        )

        assert result.exit_code == 0
        assert f"{PRIVATE_ALBUM}" in result.output.split("Skipped")[1]


class TestCollectionCheck:
    def test_success_line_keeps_private_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gallery = _gallery(tmp_path)
        collection = gallery / "collections" / "Best of [private]"
        collection.mkdir(parents=True)
        assert (
            runner.invoke(app, ["collection", "init", "-c", str(collection)]).exit_code
            == 0
        )
        monkeypatch.chdir(gallery)

        result = runner.invoke(
            app, ["collection", "check", "-c", str(collection), "-g", str(gallery)]
        )

        assert result.exit_code == 0, result.output
        assert "collections/Best of [private]" in result.output


class TestStatsTable:
    def test_collection_row_keeps_private_tag(self) -> None:
        stats = GalleryCollectionStats(
            total=1,
            by_combination={
                (
                    CollectionMembers.MANUAL,
                    CollectionLifecycle.EXPLICIT,
                    CollectionStrategy.IMPORT,
                ): 1
            },
            total_album_refs=0,
            total_collection_refs=0,
            total_image_refs=0,
            total_video_refs=0,
            collections=(
                CollectionStatsEntry(
                    name="Best of [private]",
                    members=CollectionMembers.MANUAL,
                    lifecycle=CollectionLifecycle.EXPLICIT,
                    strategy=CollectionStrategy.IMPORT,
                    album_count=0,
                    collection_count=0,
                    image_count=0,
                    video_count=0,
                ),
            ),
        )
        out = StringIO()
        Console(file=out, width=200).print(format_collections_table(stats))
        assert "Best of [private]" in out.getvalue()
