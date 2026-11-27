import csv
import io
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import Result

from photree.album.id import format_album_external_id, generate_album_id
from photree.album.refresh import refresh_album_derived_data
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
)
from photree.foundation.linking import LinkMode
from tests.fakes import invoke_cli
from tests.testkit import make_gallery, write_file


def _setup_album(base_dir: Path, name: str) -> Path:
    """Create an album with one iOS picture and its browsable copy and JPEG."""
    album_dir = base_dir / name
    write_file(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC", "x" * 2048)
    write_file(album_dir / "main-img" / "IMG_0001.HEIC", "x" * 2048)
    write_file(album_dir / "main-jpg" / "IMG_0001.jpg", "y" * 512)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    return album_dir


class TestAlbumStats:
    def test_album_stats_prints_the_tables(self, tmp_path: Path) -> None:
        album_dir = _setup_album(tmp_path, "2024-06-15 - Hiking")

        result = invoke_cli(["album", "stats", "--album-dir", str(album_dir)])

        assert result.exit_code == 0, result.output
        assert "Overview" in result.output
        assert "By Media Source" in result.output
        assert "4.50 KiB" in result.output  # apparent size: 2048 + 2048 + 512

    def test_album_stats_exits_1_when_the_name_cannot_be_parsed(
        self,
        tmp_path: Path,
    ) -> None:
        album_dir = _setup_album(tmp_path, "not an album name")

        result = invoke_cli(["album", "stats", "--album-dir", str(album_dir)])

        assert result.exit_code == 1
        assert 'Album name "not an album name" cannot be parsed.' in result.output


_CSV_LISTINGS = [
    ("list-albums", "No albums found.", "id,path,"),
    ("list-media", "No albums found.", "album_id,media_source,type,id,key"),
    ("list-collections", "No collections found.", "id,path,date,"),
]


class TestEmptyCsvListings:
    @pytest.mark.parametrize(("command", "notice", "header"), _CSV_LISTINGS)
    def test_empty_csv_still_has_its_header(
        self,
        tmp_path: Path,
        command: str,
        notice: str,
        header: str,
    ) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)

        result = invoke_cli(
            ["gallery", command, "--output", "csv", "--gallery-dir", str(gallery)],
        )

        assert result.exit_code == 0, result.output
        assert result.stdout.startswith(header)
        assert len(result.stdout.splitlines()) == 1
        assert notice in result.stderr

    @pytest.mark.parametrize(("command", "notice", "header"), _CSV_LISTINGS)
    def test_empty_csv_output_file_is_written(
        self,
        tmp_path: Path,
        command: str,
        notice: str,
        header: str,
    ) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        out = tmp_path / "out.csv"

        result = invoke_cli(
            [
                "gallery",
                command,
                "--output",
                "csv",
                "--gallery-dir",
                str(gallery),
                "--file",
                str(out),
            ],
        )

        assert result.exit_code == 0, result.output
        assert out.read_text(encoding="utf-8").startswith(header)
        assert notice in result.stderr


@dataclass(frozen=True)
class _Gallery:
    root: Path
    album: Path
    album_id: str
    collection: Path


@pytest.fixture
def gallery(tmp_path: Path) -> _Gallery:
    """Build a gallery holding one refreshed std album and a collection of it."""
    root = make_gallery(tmp_path, faces_enabled=False)
    album = root / "albums" / "2024" / "2024-06-15 - Hiking"
    write_file(album / "std-main" / "orig-img" / "DSC_0001.jpg", "x" * 3000)
    album_id = generate_album_id()
    save_album_metadata(album, AlbumMetadata(id=album_id))
    refresh_album_derived_data(album, link_mode=LinkMode.HARDLINK)
    collection = root / "collections" / "2024" / "2024-06 - Summer [x]"
    collection.mkdir(parents=True)
    save_collection_metadata(
        collection,
        CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
            albums=[album_id],
        ),
    )
    return _Gallery(root, album, album_id, collection)


def _invoke(*args: str) -> Result:
    result = invoke_cli(list(args))
    assert result.exit_code == 0, result.output
    return result


class TestGalleryReports:
    def test_show_prints_the_gallery_settings(self, gallery: _Gallery) -> None:
        result = _invoke("gallery", "show", "--gallery-dir", str(gallery.root))

        assert "link-mode: hardlink" in result.output
        assert "albums: 1" in result.output

    def test_stats_prints_album_and_collection_sections(
        self,
        gallery: _Gallery,
    ) -> None:
        result = _invoke("gallery", "stats", "--gallery-dir", str(gallery.root))

        assert "Overview" in result.output
        assert "By Year" in result.output
        assert "Collections: 1" in result.output
        assert "Album refs: 1" in result.output

    def test_list_albums_prints_each_album_with_its_id(
        self,
        gallery: _Gallery,
    ) -> None:
        result = _invoke("gallery", "list-albums", "--gallery-dir", str(gallery.root))

        assert "Found 1 album(s)." in result.output
        assert "albums/2024/2024-06-15 - Hiking" in result.output
        assert f"id: {format_album_external_id(gallery.album_id)}" in result.output

    def test_list_media_prints_each_media_id(self, gallery: _Gallery) -> None:
        result = _invoke("gallery", "list-media", "--gallery-dir", str(gallery.root))

        assert "main:" in result.output
        assert "image_" in result.output
        assert ": DSC_0001" in result.output

    def test_list_collections_prints_each_collection_metadata(
        self,
        gallery: _Gallery,
    ) -> None:
        result = _invoke(
            "gallery",
            "list-collections",
            "--gallery-dir",
            str(gallery.root),
        )

        assert "Found 1 collection(s)." in result.output
        assert "2024-06 - Summer [x]" in result.output
        assert "members: albums=1" in result.output


class TestAlbumsReports:
    def test_stats_prints_the_tables(self, gallery: _Gallery) -> None:
        result = _invoke("albums", "stats", "--dir", str(gallery.root / "albums"))

        assert "✓ stats 2024/2024-06-15 - Hiking" in result.output
        assert "Overview" in result.output

    def test_list_media_csv_has_a_row_per_media(self, gallery: _Gallery) -> None:
        result = _invoke(
            "albums",
            "list-media",
            "--dir",
            str(gallery.root / "albums"),
            "--output",
            "csv",
        )

        rows = list(csv.reader(io.StringIO(result.stdout)))
        assert rows[0] == ["album_id", "media_source", "type", "id", "key"]
        assert [row[:3] for row in rows[1:]] == [
            [format_album_external_id(gallery.album_id), "main", "image"],
        ]
        assert rows[1][4] == "DSC_0001"


class TestCollectionReports:
    def test_show_prints_the_collection_metadata(self, gallery: _Gallery) -> None:
        result = _invoke(
            "collection",
            "show",
            "--collection-dir",
            str(gallery.collection),
        )

        assert "directory: 2024-06 - Summer [x]" in result.output
        assert "lifecycle: explicit" in result.output
        assert "albums: 1" in result.output

    def test_collections_check_passes_a_consistent_gallery(
        self,
        gallery: _Gallery,
    ) -> None:
        result = _invoke("collections", "check", "--gallery-dir", str(gallery.root))

        assert "2024-06 - Summer [x]" in result.output
        assert "1 collection(s) checked, 0 with issues." in result.output
