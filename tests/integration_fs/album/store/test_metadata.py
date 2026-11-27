from pathlib import Path

import pytest
import yaml

from photree.album.id import (
    generate_album_id,
)
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import ALBUM_YAML, AlbumMetadata
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    InvalidMetadataError,
)


class TestAlbumMetadata:
    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        meta = AlbumMetadata(id=generate_album_id())

        save_album_metadata(album, meta)
        loaded = load_album_metadata(album)

        assert loaded is not None
        assert loaded.id == meta.id

    def test_yaml_uses_kebab_case(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id="test-id"))

        raw = yaml.safe_load((album / PHOTREE_DIR / ALBUM_YAML).read_text())
        assert "id" in raw

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_album_metadata(tmp_path) is None

    def test_load_empty_file_raises(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("")
        with pytest.raises(InvalidMetadataError) as exc_info:
            load_album_metadata(tmp_path)
        assert exc_info.value.path == photree_dir / ALBUM_YAML

    def test_load_truncated_file_raises(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("id: [0192d4e1", encoding="utf-8")
        with pytest.raises(InvalidMetadataError) as exc_info:
            load_album_metadata(tmp_path)
        assert exc_info.value.path == photree_dir / ALBUM_YAML

    def test_load_mapping_without_id_raises(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("other: 1\n", encoding="utf-8")
        with pytest.raises(InvalidMetadataError):
            load_album_metadata(tmp_path)

    def test_save_creates_photree_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id="test"))
        assert (album / PHOTREE_DIR / ALBUM_YAML).is_file()
