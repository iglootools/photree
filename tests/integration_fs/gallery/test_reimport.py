"""Tests for photree.gallery.importer.reimport_album."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.album.jpeg import noop_convert_single
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import load_album_metadata
from photree.gallery.importer import (
    compute_target_dir,
    import_album,
    reimport_album,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_gallery(tmp_path: Path) -> Path:
    from photree.fsprotocol import GalleryMetadata, LinkMode, save_gallery_metadata

    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK))
    return gallery


def _setup_ios_album(album: Path) -> None:
    _write(album / "ios-main/orig-img/IMG_0001.HEIC", "heic-data")
    _write(album / "main-img/IMG_0001.HEIC", "heic-data")
    _write(album / "main-jpg/IMG_0001.jpg", "jpg-data")
    (album / "ios-main/orig-vid").mkdir(parents=True, exist_ok=True)
    (album / "main-vid").mkdir(parents=True, exist_ok=True)


def _uuid_for_key(target: Path, key: str) -> str | None:
    media = load_media_metadata(target)
    assert media is not None
    images = media.media_sources["main"].images
    return next((uuid for uuid, k in images.items() if k == key), None)


def _first_import(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Import a minimal album. Returns (gallery, source, target)."""
    gallery = _setup_gallery(tmp_path)
    source = tmp_path / "2024-07-14 - Hiking"
    _setup_ios_album(source)
    result = import_album(
        source_dir=source, gallery_dir=gallery, convert_file=noop_convert_single
    )
    return gallery, source, result.target_dir


class TestReimportAlbum:
    def test_preserves_id_and_existing_uuids(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        original_id = load_album_metadata(target).id  # type: ignore[union-attr]
        uuid_0001 = _uuid_for_key(target, "0001")

        # Add a new image to the source.
        _write(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")
        _write(source / "main-img/IMG_0002.HEIC", "heic2")

        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        meta = load_album_metadata(target)
        assert meta is not None and meta.id == original_id
        # Existing key keeps its UUID; new key gets one.
        assert _uuid_for_key(target, "0001") == uuid_0001
        assert _uuid_for_key(target, "0002") is not None
        assert (target / "ios-main/orig-img/IMG_0002.HEIC").is_file()

    def test_prunes_removed_files(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        _write(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")
        _write(source / "main-img/IMG_0002.HEIC", "heic2")
        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )
        uuid_0001 = _uuid_for_key(target, "0001")

        # Remove 0002 from the source and reimport again.
        (source / "ios-main/orig-img/IMG_0002.HEIC").unlink()
        (source / "main-img/IMG_0002.HEIC").unlink()
        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        assert _uuid_for_key(target, "0002") is None
        assert _uuid_for_key(target, "0001") == uuid_0001
        assert not (target / "ios-main/orig-img/IMG_0002.HEIC").exists()

    def test_drops_stale_browsable_files(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        # Add a file directly to the gallery copy that is absent from source.
        _write(target / "ios-main/orig-img/IMG_0099.HEIC", "stale")
        _write(target / "main-img/IMG_0099.HEIC", "stale")

        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        # Reimport mirrors the source, so the stale gallery-only file is gone.
        assert not (target / "ios-main/orig-img/IMG_0099.HEIC").exists()
        assert (target / "ios-main/orig-img/IMG_0001.HEIC").is_file()

    def test_atomic_on_refresh_failure(self, tmp_path: Path, monkeypatch) -> None:
        gallery, source, target = _first_import(tmp_path)
        original_id = load_album_metadata(target).id  # type: ignore[union-attr]
        _write(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")

        def boom(*_args, **_kwargs):
            raise RuntimeError("refresh failed")

        monkeypatch.setattr("photree.album.refresh.refresh_album_derived_data", boom)

        with pytest.raises(RuntimeError, match="refresh failed"):
            reimport_album(
                source_dir=source,
                gallery_dir=gallery,
                existing_dir=target,
                convert_file=noop_convert_single,
            )

        # Original gallery copy is untouched, no staging/backup leftovers.
        meta = load_album_metadata(target)
        assert meta is not None and meta.id == original_id
        assert (target / "ios-main/orig-img/IMG_0001.HEIC").is_file()
        assert not (target.parent / ".2024-07-14 - Hiking.reimport").exists()
        assert not (target.parent / ".2024-07-14 - Hiking.old").exists()

    def test_dry_run_mutates_nothing(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        _write(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")

        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            dry_run=True,
            convert_file=noop_convert_single,
        )

        # The new file was not propagated into the gallery.
        assert not (target / "ios-main/orig-img/IMG_0002.HEIC").exists()

    def test_rename_moves_album_and_keeps_id(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        original_id = load_album_metadata(target).id  # type: ignore[union-attr]

        # The source is renamed (same date, new title) but is the same album.
        renamed = source.parent / "2024-07-14 - Hiking the Rockies"
        source.rename(renamed)
        new_target = compute_target_dir(gallery, renamed.name)

        reimport_album(
            source_dir=renamed,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        assert not target.exists()
        assert new_target.is_dir()
        meta = load_album_metadata(new_target)
        assert meta is not None and meta.id == original_id
