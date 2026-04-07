"""Tests for gallery browsable directory rendering."""

from __future__ import annotations

from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from photree.fsprotocol import BROWSABLE_DIR, GalleryMetadata, save_gallery_metadata
from photree.gallery.browsable_refresh import refresh_browsable


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata())
    return gallery


def _setup_album(
    gallery: Path, name: str, *, private: bool = False
) -> tuple[Path, str]:
    tag = " [private]" if private else ""
    full_name = f"{name}{tag}"
    album_dir = gallery / "albums" / "2024" / full_name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)
    _write(album_dir / "main-jpg" / "IMG_0001.jpg")
    (album_dir / "main-vid").mkdir(parents=True, exist_ok=True)
    aid = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return album_dir, aid


class TestBrowsableRefreshAlbums:
    def test_renders_public_album(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Trip")

        result = refresh_browsable(gallery)
        assert result.success
        assert result.albums_rendered == 1
        assert result.symlinks_created > 0

        # Check structure
        album_browsable = (
            gallery
            / BROWSABLE_DIR
            / "public"
            / "albums"
            / "by-year"
            / "2024"
            / "2024-07-14 - Trip"
        )
        assert (album_browsable / "main-jpg").is_symlink()
        assert (album_browsable / "main-vid").is_symlink()
        # main-img should NOT be present
        assert not (album_browsable / "main-img").exists()

    def test_renders_private_album_under_private(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Secret", private=True)

        result = refresh_browsable(gallery)
        assert result.success

        private_album = (
            gallery
            / BROWSABLE_DIR
            / "private"
            / "albums"
            / "by-year"
            / "2024"
            / "2024-07-14 - Secret [private]"
        )
        assert (private_album / "main-jpg").is_symlink()

        # Should NOT be under public
        public_path = gallery / BROWSABLE_DIR / "public" / "albums" / "by-year" / "2024"
        assert not public_path.exists()

    def test_symlinks_are_relative(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Trip")

        refresh_browsable(gallery)

        link = (
            gallery
            / BROWSABLE_DIR
            / "public"
            / "albums"
            / "by-year"
            / "2024"
            / "2024-07-14 - Trip"
            / "main-jpg"
        )
        target = link.resolve()
        # Should resolve to the actual album's main-jpg
        assert target.name == "main-jpg"
        assert "albums" in str(target)


class TestBrowsableRefreshCollections:
    def test_renders_collection_with_album_members(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid = _setup_album(gallery, "2024-07-14 - Trip")

        col_dir = gallery / "collections" / "2024" / "2024-07 - Summer"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[aid],
            ),
        )

        result = refresh_browsable(gallery)
        assert result.success
        assert result.collections_rendered == 1

        col_browsable = (
            gallery
            / BROWSABLE_DIR
            / "public"
            / "collections"
            / "by-year"
            / "2024"
            / "2024-07 - Summer"
        )
        assert (
            col_browsable / "albums" / "2024-07-14 - Trip" / "main-jpg"
        ).is_symlink()

    def test_renders_dateless_collection_under_all_time(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid = _setup_album(gallery, "2024-07-14 - Trip")

        col_dir = gallery / "collections" / "Best of All Time"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[aid],
            ),
        )

        result = refresh_browsable(gallery)
        assert result.success

        col_browsable = (
            gallery
            / BROWSABLE_DIR
            / "public"
            / "collections"
            / "all-time"
            / "Best of All Time"
        )
        assert (
            col_browsable / "albums" / "2024-07-14 - Trip" / "main-jpg"
        ).is_symlink()

    def test_renders_chapter_under_by_chapter(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid = _setup_album(gallery, "2024-07-14 - Trip")

        col_dir = gallery / "collections" / "2024" / "2024 - Student Years"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.EXPLICIT,
                strategy=CollectionStrategy.CHAPTER,
                albums=[aid],
            ),
        )

        result = refresh_browsable(gallery)
        assert result.success

        col_browsable = (
            gallery
            / BROWSABLE_DIR
            / "public"
            / "collections"
            / "by-chapter"
            / "2024 - Student Years"
        )
        assert (col_browsable / "albums").is_dir()


class TestBrowsableRefreshCycleDetection:
    def test_detects_cycle(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)

        cid_a = generate_collection_id()
        cid_b = generate_collection_id()

        col_a = gallery / "collections" / "2024" / "2024 - A"
        col_a.mkdir(parents=True)
        save_collection_metadata(
            col_a,
            CollectionMetadata(
                id=cid_a,
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                collections=[cid_b],
            ),
        )

        col_b = gallery / "collections" / "2024" / "2024 - B"
        col_b.mkdir(parents=True)
        save_collection_metadata(
            col_b,
            CollectionMetadata(
                id=cid_b,
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                collections=[cid_a],
            ),
        )

        result = refresh_browsable(gallery)
        assert not result.success
        assert any("cycle" in e.message for e in result.errors)


class TestBrowsableRefreshSafetyCheck:
    def test_rejects_dir_with_regular_files(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        browsable = gallery / BROWSABLE_DIR
        browsable.mkdir()
        (browsable / "regular_file.txt").write_text("danger")

        result = refresh_browsable(gallery)
        assert not result.success
        assert any("regular file" in e.message for e in result.errors)

    def test_allows_empty_dir(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        (gallery / BROWSABLE_DIR).mkdir()

        result = refresh_browsable(gallery)
        assert result.success


class TestBrowsableRefreshDryRun:
    def test_dry_run_does_not_create_browsable(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Trip")

        result = refresh_browsable(gallery, dry_run=True)
        assert result.success
        assert result.albums_rendered == 1
        assert not (gallery / BROWSABLE_DIR).exists()
