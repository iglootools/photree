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
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from photree.fsprotocol import GalleryMetadata, save_gallery_metadata


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
            members=kwargs.get("members", CollectionMembers.MANUAL),
            lifecycle=kwargs.get("lifecycle", CollectionLifecycle.EXPLICIT),
            strategy=kwargs.get("strategy", CollectionStrategy.IMPORT),
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
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[album_id],
            ),
        )

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success


class TestCheckCollectionConfig:
    def test_implicit_smart_passes(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(
            gallery,
            "2024-07 - July",
            members=CollectionMembers.SMART,
            lifecycle=CollectionLifecycle.IMPLICIT,
            strategy=CollectionStrategy.ALBUM_SERIES,
        )
        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success

    def test_implicit_manual_fails(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir = gallery / "collections" / "2024" / "2024-07 - July"
        col_dir.mkdir(parents=True)
        # Manually write invalid combination (bypassing validation)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.IMPLICIT,
            ),
        )
        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert not result.success
        assert any(i.code == "invalid-collection-config" for i in result.issues)


class TestCheckEmpty:
    def test_empty_collection_passes(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(gallery, "2024-07 - July")

        lookup = build_gallery_lookup(gallery)
        result = check_collection(col_dir, lookup)
        assert result.success


def _setup_chapter(gallery: Path, year: str, name: str) -> tuple[Path, str]:
    col_dir = gallery / "collections" / year / name
    col_dir.mkdir(parents=True)
    cid = generate_collection_id()
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=cid,
            members=CollectionMembers.SMART,
            lifecycle=CollectionLifecycle.EXPLICIT,
            strategy=CollectionStrategy.CHAPTER,
        ),
    )
    return col_dir, cid


class TestCheckChapterOverlap:
    def test_overlap_across_year_directories_detected(self, tmp_path: Path) -> None:
        # Regression: chapters were only compared with siblings in the same
        # collections/YYYY/ directory, so these two never conflicted.
        gallery = _setup_gallery(tmp_path)
        montreal, _ = _setup_chapter(gallery, "2019", "2019--2022 - Montreal")
        _setup_chapter(gallery, "2021", "2021--2023 - Toronto")

        result = check_collection(montreal, build_gallery_lookup(gallery))

        assert [i.code for i in result.issues] == ["chapter-date-overlap"]

    def test_non_overlapping_chapters_pass(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        montreal, _ = _setup_chapter(gallery, "2019", "2019--2020 - Montreal")
        toronto, _ = _setup_chapter(gallery, "2021", "2021--2023 - Toronto")
        lookup = build_gallery_lookup(gallery)

        assert check_collection(montreal, lookup).success
        assert check_collection(toronto, lookup).success

    def test_chapters_sharing_one_boundary_day_overlap(self, tmp_path: Path) -> None:
        # Both ranges include 2019-06-30, so the life period is claimed twice.
        gallery = _setup_gallery(tmp_path)
        paris, _ = _setup_chapter(gallery, "2017", "2017-01-01--2019-06-30 - Paris")
        _setup_chapter(gallery, "2019", "2019-06-30--2022-12-31 - Montreal")

        result = check_collection(paris, build_gallery_lookup(gallery))

        assert [i.code for i in result.issues] == ["chapter-date-overlap"]

    def test_adjacent_chapters_pass(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        paris, _ = _setup_chapter(gallery, "2017", "2017-01-01--2019-06-29 - Paris")
        montreal, _ = _setup_chapter(
            gallery, "2019", "2019-06-30--2022-12-31 - Montreal"
        )
        lookup = build_gallery_lookup(gallery)

        assert check_collection(paris, lookup).success
        assert check_collection(montreal, lookup).success

    def test_date_range_collection_does_not_count_as_chapter(
        self, tmp_path: Path
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        montreal, _ = _setup_chapter(gallery, "2019", "2019--2022 - Montreal")
        _setup_collection(
            gallery,
            "2020 - Year",
            members=CollectionMembers.SMART,
            strategy=CollectionStrategy.DATE_RANGE,
        )

        assert check_collection(montreal, build_gallery_lookup(gallery)).success


class TestCheckInvalidMetadata:
    def test_corrupt_metadata_reported_not_crashing(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir, _ = _setup_collection(gallery, "2024-07 - July")
        (col_dir / ".photree" / "collection.yaml").write_text(
            "- not a mapping\n", encoding="utf-8"
        )

        result = check_collection(col_dir, build_gallery_lookup(gallery))

        assert [i.code for i in result.issues] == ["invalid-metadata"]
