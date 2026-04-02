"""Tests for metadata models, ID helpers, and album detection."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml

from photree.common.base58 import base58_decode, base58_encode
from photree.album.store.album_discovery import (
    discover_albums,
    discover_potential_albums,
    has_media_sources,
    is_album,
)
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.id import (
    format_album_external_id,
    format_external_id,
    generate_album_id,
    parse_external_id,
)
from photree.album.store.protocol import ALBUM_YAML, AlbumMetadata
from photree.fsprotocol import LinkMode, PHOTREE_DIR
from photree.fsprotocol import load_gallery_metadata, save_gallery_metadata
from photree.fsprotocol import (
    resolve_gallery_dir,
    resolve_gallery_metadata,
    resolve_link_mode,
)
from photree.fsprotocol import GalleryMetadata


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _mark_album(album_dir: Path) -> None:
    """Create .photree/album.yaml with a generated ID."""
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))


def _setup_media_source(album_dir: Path) -> None:
    """Create a minimal iOS media source so the album is detected."""
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


class TestBase58:
    def test_roundtrip(self) -> None:
        data = uuid.uuid4().bytes
        assert base58_decode(base58_encode(data)) == data

    def test_known_value(self) -> None:
        data = b"\x00\x01"
        encoded = base58_encode(data)
        assert encoded.startswith("1")
        assert base58_decode(encoded) == data

    def test_empty_input(self) -> None:
        assert base58_encode(b"") == ""

    def test_leading_zeros(self) -> None:
        data = b"\x00\x00\x01"
        encoded = base58_encode(data)
        assert encoded.startswith("11")
        assert base58_decode(encoded) == data


class TestExternalId:
    def test_roundtrip(self) -> None:
        internal = str(uuid.uuid4())
        external = format_external_id("album", internal)
        assert parse_external_id(external, "album") == internal

    def test_format_starts_with_prefix(self) -> None:
        internal = str(uuid.uuid4())
        external = format_album_external_id(internal)
        assert external.startswith("album_")

    def test_reasonable_length(self) -> None:
        internal = str(uuid.uuid4())
        external = format_album_external_id(internal)
        # prefix (5) + underscore (1) + base58 (~22) = ~28 chars
        assert 20 < len(external) < 35

    def test_parse_wrong_prefix_raises(self) -> None:
        internal = str(uuid.uuid4())
        external = format_external_id("album", internal)
        try:
            parse_external_id(external, "gallery")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_parse_no_underscore_raises(self) -> None:
        try:
            parse_external_id("nounderscore", "album")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


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

    def test_load_empty_file_returns_none(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("")
        assert load_album_metadata(tmp_path) is None

    def test_save_creates_photree_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id="test"))
        assert (album / PHOTREE_DIR / ALBUM_YAML).is_file()


class TestGalleryMetadata:
    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / PHOTREE_DIR / "gallery.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            yaml.safe_dump(
                GalleryMetadata(link_mode=LinkMode.SYMLINK).model_dump(
                    by_alias=True, mode="json"
                ),
                default_flow_style=False,
                sort_keys=False,
            )
        )

        loaded = load_gallery_metadata(path)
        assert loaded.link_mode == LinkMode.SYMLINK

    def test_yaml_uses_kebab_case(self, tmp_path: Path) -> None:
        meta = GalleryMetadata(link_mode=LinkMode.COPY)
        dumped = yaml.safe_dump(
            meta.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
        assert "link-mode" in dumped
        assert "link_mode" not in dumped

    def test_default_link_mode_is_hardlink(self) -> None:
        meta = GalleryMetadata()
        assert meta.link_mode == LinkMode.HARDLINK


class TestResolveGalleryMetadata:
    def test_no_gallery_yaml_returns_none(self, tmp_path: Path) -> None:
        assert resolve_gallery_metadata(tmp_path) is None

    def test_finds_gallery_yaml_in_parent(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: symlink\n")

        child = tmp_path / "subdir"
        child.mkdir()

        result = resolve_gallery_metadata(child)
        assert result is not None
        assert result.link_mode == LinkMode.SYMLINK

    def test_finds_gallery_yaml_in_grandparent(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: copy\n")

        grandchild = tmp_path / "a" / "b"
        grandchild.mkdir(parents=True)

        result = resolve_gallery_metadata(grandchild)
        assert result is not None
        assert result.link_mode == LinkMode.COPY


class TestResolveLinkMode:
    def test_explicit_overrides_gallery(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: symlink\n")

        assert resolve_link_mode(LinkMode.COPY, tmp_path) == LinkMode.COPY

    def test_gallery_overrides_default(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: symlink\n")

        assert resolve_link_mode(None, tmp_path) == LinkMode.SYMLINK

    def test_fallback_to_hardlink(self, tmp_path: Path) -> None:
        assert resolve_link_mode(None, tmp_path) == LinkMode.HARDLINK


class TestGenerateAlbumId:
    def test_returns_valid_uuid(self) -> None:
        aid = generate_album_id()
        parsed = uuid.UUID(aid)
        assert parsed.version == 7


class TestIsAlbum:
    def test_album_with_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        _mark_album(album)
        assert is_album(album)

    def test_legacy_album_not_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        (album / PHOTREE_DIR).mkdir(parents=True, exist_ok=True)
        assert not is_album(album)

    def test_no_media_source_not_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
        assert not is_album(album)


class TestResolveGalleryDir:
    def test_explicit_dir_with_gallery_yaml(self, tmp_path: Path) -> None:
        save_gallery_metadata(tmp_path, GalleryMetadata())
        assert resolve_gallery_dir(tmp_path) == tmp_path

    def test_explicit_dir_without_gallery_yaml_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No gallery metadata"):
            resolve_gallery_dir(tmp_path)

    def test_resolves_from_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_gallery_metadata(tmp_path, GalleryMetadata())
        child = tmp_path / "subdir"
        child.mkdir()
        monkeypatch.chdir(child)
        assert resolve_gallery_dir(None) == tmp_path

    def test_no_gallery_found_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="No gallery metadata"):
            resolve_gallery_dir(None)


class TestDiscoverAlbums:
    def test_discovers_proper_albums(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        _mark_album(album)

        albums = discover_albums(tmp_path)
        assert albums == [album]

    def test_skips_legacy_albums(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        (album / PHOTREE_DIR).mkdir(parents=True, exist_ok=True)

        albums = discover_albums(tmp_path)
        assert albums == []


class TestHasMediaSources:
    def test_with_ios_media_source(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        assert has_media_sources(album) is True

    def test_empty_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        assert has_media_sources(album) is False


class TestDiscoverPotentialAlbums:
    def test_finds_albums_without_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        # No _mark_album — no album.yaml

        result = discover_potential_albums(tmp_path)
        assert result == [album]

    def test_finds_albums_with_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_media_source(album)
        _mark_album(album)

        result = discover_potential_albums(tmp_path)
        assert result == [album]

    def test_skips_empty_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        result = discover_potential_albums(tmp_path)
        assert result == []
