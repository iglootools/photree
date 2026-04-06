"""Tests for collection check."""

from __future__ import annotations

from pathlib import Path

from photree.album.id import generate_album_id, generate_media_id
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    save_media_metadata,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.check import build_gallery_lookup, check_collection
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)
from photree.fsprotocol import GalleryMetadata, save_gallery_metadata


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata())
    return gallery


def _setup_album(gallery: Path, name: str) -> tuple[Path, str]:
    album_dir = gallery / "albums" / "2024" / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)
    aid = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return album_dir, aid


def _setup_collection(
    gallery: Path,
    name: str,
    **kwargs: object,
) -> tuple[Path, str]:
    col_dir = gallery / "collections" / "2024" / name
    col_dir.mkdir(parents=True)
    cid = generate_collection_id()
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=cid,
            kind=kwargs.get("kind", CollectionKind.MANUAL),
            lifecycle=kwargs.get("lifecycle", CollectionLifecycle.EXPLICIT),
            albums=kwargs.get("albums", []),
            collections=kwargs.get("collections", []),
            images=kwargs.get("images", []),
            videos=kwargs.get("videos", []),
        ),
    )
    return col_dir, cid


class TestCheckMemberExistence:
    def test_valid_album_member(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        col_dir, _ = _setup_collection(gallery, "2024-07 - July", albums=[album_id])

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success

    def test_missing_album_member(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(
            gallery, "2024-07 - July", albums=["nonexistent-id"]
        )

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert not result.success
        assert any(i.code == "missing-album" for i in result.issues)

    def test_missing_image_member(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(
            gallery, "2024-07 - July", images=["nonexistent-id"]
        )

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert not result.success
        assert any(i.code == "missing-image" for i in result.issues)

    def test_valid_image_member(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album_dir, _ = _setup_album(gallery, "2024-07-14 - Trip")
        img_id = generate_media_id()
        save_media_metadata(
            album_dir,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={img_id: "0001"})
                }
            ),
        )
        col_dir, _ = _setup_collection(gallery, "2024-07 - July", images=[img_id])

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success

    def test_missing_collection_member(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(
            gallery, "2024-07 - July", collections=["nonexistent-id"]
        )

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert not result.success
        assert any(i.code == "missing-collection" for i in result.issues)


class TestCheckDateCoverage:
    def test_album_within_range(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        col_dir, _ = _setup_collection(gallery, "2024-07 - July", albums=[album_id])

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success

    def test_album_outside_range(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-08-01 - August Trip")
        col_dir, _ = _setup_collection(gallery, "2024-07 - July", albums=[album_id])

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert not result.success
        assert any(i.code == "date-not-covered" for i in result.issues)

    def test_dateless_collection_skips_date_check(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        col_dir = gallery / "collections" / "Best Of"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                kind=CollectionKind.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[album_id],
            ),
        )

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success


class TestCheckEmpty:
    def test_empty_collection_passes(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(gallery, "2024-07 - July")

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success
