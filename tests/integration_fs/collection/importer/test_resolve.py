"""Tests for collection import member resolution."""

from __future__ import annotations

from pathlib import Path

from photree.album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
    generate_album_id,
    generate_media_id,
)
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    save_media_metadata,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.id import (
    format_collection_external_id,
    generate_collection_id,
)
from photree.collection.importer.resolve import resolve_entries
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)
from photree.fsprotocol import save_gallery_metadata, GalleryMetadata


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata())
    return gallery


def _setup_album(
    gallery: Path, name: str, album_id: str | None = None
) -> tuple[Path, str]:
    """Create an album in the gallery with media sources."""
    album_dir = gallery / "albums" / "2024" / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)
    aid = album_id or generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return album_dir, aid


def _setup_album_with_media(gallery: Path, name: str) -> tuple[Path, str, str, str]:
    """Create album with media metadata. Returns (dir, album_id, image_id, video_id)."""
    album_dir, album_id = _setup_album(gallery, name)
    img_id = generate_media_id()
    vid_id = generate_media_id()
    save_media_metadata(
        album_dir,
        MediaMetadata(
            media_sources={
                "main": MediaSourceMediaMetadata(
                    images={img_id: "0001"},
                    videos={vid_id: "0002"},
                )
            }
        ),
    )
    return album_dir, album_id, img_id, vid_id


def _setup_collection(gallery: Path, name: str) -> tuple[Path, str]:
    col_dir = gallery / "collections" / "2024" / name
    col_dir.mkdir(parents=True)
    cid = generate_collection_id()
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=cid,
            kind=CollectionKind.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        ),
    )
    return col_dir, cid


class TestResolveByExternalId:
    def test_resolve_album_by_external_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        ext_id = format_album_external_id(album_id)

        result = resolve_entries((ext_id,), gallery)
        assert result.success
        assert result.members.albums == (album_id,)

    def test_resolve_collection_by_external_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, col_id = _setup_collection(gallery, "2024 - Best Of")

        ext_id = format_collection_external_id(col_id)
        result = resolve_entries((ext_id,), gallery)
        assert result.success
        assert result.members.collections == (col_id,)

    def test_resolve_image_by_external_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, _, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        ext_id = format_image_external_id(img_id)
        result = resolve_entries((ext_id,), gallery)
        assert result.success
        assert result.members.images == (img_id,)

    def test_resolve_video_by_external_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, _, _, vid_id = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        ext_id = format_video_external_id(vid_id)
        result = resolve_entries((ext_id,), gallery)
        assert result.success
        assert result.members.videos == (vid_id,)


class TestResolveByInternalId:
    def test_resolve_album_by_uuid(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")

        result = resolve_entries((album_id,), gallery)
        assert result.success
        assert result.members.albums == (album_id,)

    def test_resolve_image_by_uuid(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, _, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        result = resolve_entries((img_id,), gallery)
        assert result.success
        assert result.members.images == (img_id,)


class TestResolveByName:
    def test_resolve_album_by_dir_name(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")

        result = resolve_entries(("2024-07-14 - Trip",), gallery)
        assert result.success
        assert result.members.albums == (album_id,)

    def test_resolve_collection_by_dir_name(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, col_id = _setup_collection(gallery, "2024 - Best Of")

        result = resolve_entries(("2024 - Best Of",), gallery)
        assert result.success
        assert result.members.collections == (col_id,)


class TestResolveMixed:
    def test_resolve_mixed_entries(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")
        _, col_id = _setup_collection(gallery, "2024 - Best Of")

        result = resolve_entries(
            (
                "2024-07-14 - Trip",
                format_collection_external_id(col_id),
                format_image_external_id(img_id),
            ),
            gallery,
        )
        assert result.success
        assert result.members.albums == (album_id,)
        assert result.members.collections == (col_id,)
        assert result.members.images == (img_id,)


class TestResolveErrors:
    def test_unresolved_entry(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)

        result = resolve_entries(("nonexistent",), gallery)
        assert not result.success
        assert len(result.errors) == 1
        assert "not found" in result.errors[0].message

    def test_unresolved_external_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        fake_id = format_album_external_id(generate_album_id())

        result = resolve_entries((fake_id,), gallery)
        assert not result.success
        assert "not found" in result.errors[0].message

    def test_ambiguous_album_name(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        # Create two albums with the same dir name in different year buckets
        name = "2024-07-14 - Trip"
        album1 = gallery / "albums" / "2024" / name
        album2 = gallery / "albums" / "2025" / name
        _write(album1 / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        (album1 / "main-img").mkdir(parents=True, exist_ok=True)
        (album1 / "main-jpg").mkdir(parents=True, exist_ok=True)
        save_album_metadata(album1, AlbumMetadata(id=generate_album_id()))
        _write(album2 / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        (album2 / "main-img").mkdir(parents=True, exist_ok=True)
        (album2 / "main-jpg").mkdir(parents=True, exist_ok=True)
        save_album_metadata(album2, AlbumMetadata(id=generate_album_id()))

        result = resolve_entries((name,), gallery)
        assert not result.success
        assert "ambiguous" in result.errors[0].message

    def test_duplicate_entry(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        ext_id = format_album_external_id(album_id)

        # Same album referenced twice (by name and by ID)
        result = resolve_entries(("2024-07-14 - Trip", ext_id), gallery)
        assert not result.success
        assert any("duplicate" in e.message for e in result.errors)
