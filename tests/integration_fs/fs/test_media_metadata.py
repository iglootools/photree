"""Tests for media metadata models and I/O."""

from __future__ import annotations

from pathlib import Path

import yaml

from photree.album.id import generate_media_id
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
    save_media_metadata,
)
from photree.album.store.protocol import MEDIA_IDS_DIR
from photree.fsprotocol import PHOTREE_DIR


class TestMediaMetadata:
    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()

        img_id = generate_media_id()
        vid_id = generate_media_id()
        meta = MediaMetadata(
            media_sources={
                "main": MediaSourceMediaMetadata(
                    images={img_id: "0410"},
                    videos={vid_id: "0115"},
                ),
            }
        )

        save_media_metadata(album, meta)
        loaded = load_media_metadata(album)

        assert loaded is not None
        assert loaded.media_sources["main"].images[img_id] == "0410"
        assert loaded.media_sources["main"].videos[vid_id] == "0115"

    def test_per_source_files(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={"id1": "0410"}),
                    "bruno": MediaSourceMediaMetadata(images={"id2": "DSC_1234"}),
                }
            ),
        )

        ids_dir = album / PHOTREE_DIR / MEDIA_IDS_DIR
        assert (ids_dir / "main.yaml").is_file()
        assert (ids_dir / "bruno.yaml").is_file()

    def test_yaml_uses_kebab_case(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={"id1": "0410"}),
                }
            ),
        )

        raw = yaml.safe_load(
            (album / PHOTREE_DIR / MEDIA_IDS_DIR / "main.yaml").read_text()
        )
        # Per-source files contain images/videos directly (no media-sources wrapper)
        assert "images" in raw

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_media_metadata(tmp_path) is None

    def test_load_empty_dir_returns_none(self, tmp_path: Path) -> None:
        ids_dir = tmp_path / PHOTREE_DIR / MEDIA_IDS_DIR
        ids_dir.mkdir(parents=True)
        assert load_media_metadata(tmp_path) is None

    def test_save_creates_media_ids_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={"main": MediaSourceMediaMetadata(images={"id1": "0410"})}
            ),
        )
        assert (album / PHOTREE_DIR / MEDIA_IDS_DIR).is_dir()

    def test_empty_media_sources(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_media_metadata(album, MediaMetadata())
        loaded = load_media_metadata(album)
        # No files written for empty media sources
        assert loaded is None

    def test_multiple_media_sources(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        meta = MediaMetadata(
            media_sources={
                "main": MediaSourceMediaMetadata(
                    images={"id1": "0410", "id2": "0411"},
                    videos={"id3": "0115"},
                ),
                "bruno": MediaSourceMediaMetadata(
                    images={"id4": "DSC_1234"},
                    videos={},
                ),
            }
        )
        save_media_metadata(album, meta)
        loaded = load_media_metadata(album)

        assert loaded is not None
        assert len(loaded.media_sources) == 2
        assert loaded.media_sources["main"].images == {"id1": "0410", "id2": "0411"}
        assert loaded.media_sources["bruno"].videos == {}

    def test_stale_source_files_pruned(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()

        # Save with two sources
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={"id1": "0410"}),
                    "bruno": MediaSourceMediaMetadata(images={"id2": "DSC_1234"}),
                }
            ),
        )

        # Save again with only main — bruno should be removed
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={"id1": "0410"}),
                }
            ),
        )

        ids_dir = album / PHOTREE_DIR / MEDIA_IDS_DIR
        assert (ids_dir / "main.yaml").is_file()
        assert not (ids_dir / "bruno.yaml").exists()
