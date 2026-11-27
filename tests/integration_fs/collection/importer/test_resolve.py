from datetime import datetime
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
)
from photree.collection.importer.resolve import (
    ResolutionErrorKind,
    resolve_entries,
    scan_gallery,
)
from photree.collection.importer.selection import SelectionEntry
from tests.testkit import (
    make_gallery,
    make_gallery_album,
    make_gallery_collection,
    write_file,
)


def _entry(value: str, date_hint: datetime | None = None) -> SelectionEntry:
    return SelectionEntry(value=value, date_hint=date_hint)


def _setup_std_album_with_image(gallery: Path, name: str, key: str) -> str:
    """Create an album whose ``main`` media source is std. Returns the image ID."""
    album_dir = gallery / "albums" / "2024" / name
    write_file(album_dir / "std-main" / "orig-img" / f"{key}.JPG")
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    img_id = generate_media_id()
    save_media_metadata(
        album_dir,
        MediaMetadata(
            media_sources={"main": MediaSourceMediaMetadata(images={img_id: key})},
        ),
    )
    return img_id


def _setup_album_with_media(gallery: Path, name: str) -> tuple[Path, str, str, str]:
    """Create album with media metadata. Returns (dir, album_id, image_id, video_id)."""
    album_dir, album_id = make_gallery_album(gallery, name)
    img_id = generate_media_id()
    vid_id = generate_media_id()
    save_media_metadata(
        album_dir,
        MediaMetadata(
            media_sources={
                "main": MediaSourceMediaMetadata(
                    images={img_id: "0001"},
                    videos={vid_id: "0002"},
                ),
            },
        ),
    )
    return album_dir, album_id, img_id, vid_id


class TestResolveByExternalId:
    def test_resolve_album_by_external_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")
        ext_id = format_album_external_id(album_id)

        result = resolve_entries((_entry(ext_id),), scan_gallery(gallery))
        assert result.success
        assert result.members.albums == (album_id,)

    def test_resolve_collection_by_external_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, col_id = make_gallery_collection(gallery, "2024 - Best Of")

        ext_id = format_collection_external_id(col_id)
        result = resolve_entries((_entry(ext_id),), scan_gallery(gallery))
        assert result.success
        assert result.members.collections == (col_id,)

    def test_resolve_image_by_external_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, _, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        ext_id = format_image_external_id(img_id)
        result = resolve_entries((_entry(ext_id),), scan_gallery(gallery))
        assert result.success
        assert result.members.images == (img_id,)

    def test_resolve_video_by_external_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, _, _, vid_id = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        ext_id = format_video_external_id(vid_id)
        result = resolve_entries((_entry(ext_id),), scan_gallery(gallery))
        assert result.success
        assert result.members.videos == (vid_id,)


class TestResolveByInternalId:
    def test_resolve_album_by_uuid(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")

        result = resolve_entries((_entry(album_id),), scan_gallery(gallery))
        assert result.success
        assert result.members.albums == (album_id,)

    def test_resolve_image_by_uuid(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, _, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        result = resolve_entries((_entry(img_id),), scan_gallery(gallery))
        assert result.success
        assert result.members.images == (img_id,)


class TestResolveByName:
    def test_resolve_album_by_dir_name(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")

        result = resolve_entries((_entry("2024-07-14 - Trip"),), scan_gallery(gallery))
        assert result.success
        assert result.members.albums == (album_id,)

    def test_resolve_collection_by_dir_name(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, col_id = make_gallery_collection(gallery, "2024 - Best Of")

        result = resolve_entries((_entry("2024 - Best Of"),), scan_gallery(gallery))
        assert result.success
        assert result.members.collections == (col_id,)


class TestResolveByMediaFilename:
    def test_resolve_image_by_filename(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, _, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        result = resolve_entries((_entry("IMG_0001.HEIC"),), scan_gallery(gallery))
        assert result.success
        assert result.members.images == (img_id,)

    def test_resolve_video_by_filename(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, _, _, vid_id = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        result = resolve_entries((_entry("IMG_0002.MOV"),), scan_gallery(gallery))
        assert result.success
        assert result.members.videos == (vid_id,)

    def test_ambiguous_without_date_hint(self, tmp_path: Path) -> None:
        """Same image number in two albums, no date hint → ambiguous error."""
        gallery = make_gallery(tmp_path)
        album1, _aid1 = make_gallery_album(gallery, "2024-07-14 - Trip A")
        album2, _aid2 = make_gallery_album(gallery, "2024-08-01 - Trip B")
        img_id1 = generate_media_id()
        img_id2 = generate_media_id()
        save_media_metadata(
            album1,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={img_id1: "0410"}),
                },
            ),
        )
        save_media_metadata(
            album2,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={img_id2: "0410"}),
                },
            ),
        )

        result = resolve_entries((_entry("IMG_0410.HEIC"),), scan_gallery(gallery))
        assert not result.success
        assert result.errors[0].kind == ResolutionErrorKind.AMBIGUOUS

    def test_disambiguate_with_date_hint(self, tmp_path: Path) -> None:
        """Same image number in two albums, date hint narrows to one."""
        gallery = make_gallery(tmp_path)
        album1, _aid1 = make_gallery_album(gallery, "2024-07-14 - Trip A")
        album2, _aid2 = make_gallery_album(gallery, "2024-08-01 - Trip B")
        img_id1 = generate_media_id()
        img_id2 = generate_media_id()
        save_media_metadata(
            album1,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={img_id1: "0410"}),
                },
            ),
        )
        save_media_metadata(
            album2,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={img_id2: "0410"}),
                },
            ),
        )

        # Date hint matches Trip A (July 14)
        result = resolve_entries(
            (_entry("IMG_0410.HEIC", date_hint=datetime(2024, 7, 14, 13, 55)),),
            scan_gallery(gallery),
        )
        assert result.success
        assert result.members.images == (img_id1,)

    def test_invalid_album_date_does_not_crash_date_hint(self, tmp_path: Path) -> None:
        """
        An album named with a non-existent date is skipped by the date hint.

        Regression: dates.timestamp_in_range raises on such dates, which
        crashed the whole resolution instead of narrowing to the valid album.
        """
        gallery = make_gallery(tmp_path)
        album1, _aid1 = make_gallery_album(gallery, "2024-07-14 - Trip A")
        album2, _aid2 = make_gallery_album(gallery, "2024-02-30 - Not A Day")
        img_id1 = generate_media_id()
        img_id2 = generate_media_id()
        for album, img_id in ((album1, img_id1), (album2, img_id2)):
            save_media_metadata(
                album,
                MediaMetadata(
                    media_sources={
                        "main": MediaSourceMediaMetadata(images={img_id: "0410"}),
                    },
                ),
            )

        result = resolve_entries(
            (_entry("IMG_0410.HEIC", date_hint=datetime(2024, 7, 14, 13, 55)),),
            scan_gallery(gallery),
        )

        assert result.success
        assert result.members.images == (img_id1,)

    def test_single_match_in_invalid_date_album_has_no_warning(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path)
        album, _ = make_gallery_album(gallery, "2024-02-30 - Not A Day")
        img_id = generate_media_id()
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(images={img_id: "0410"}),
                },
            ),
        )

        result = resolve_entries(
            (_entry("IMG_0410.HEIC", date_hint=datetime(2024, 7, 14, 13, 55)),),
            scan_gallery(gallery),
        )

        assert result.success
        assert result.members.images == (img_id,)
        assert result.warnings == ()

    def test_no_match_for_media_file(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - Trip")

        result = resolve_entries((_entry("IMG_9999.HEIC"),), scan_gallery(gallery))
        assert not result.success
        assert result.errors[0].kind == ResolutionErrorKind.NOT_FOUND

    def test_resolve_std_stem_based_file(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        img_id = _setup_std_album_with_image(gallery, "2024-07-14 - Trip", "DSC_1234")

        result = resolve_entries((_entry("DSC_1234.JPG"),), scan_gallery(gallery))
        assert result.success
        assert result.members.images == (img_id,)

    def test_resolve_img_prefixed_file_in_std_source(self, tmp_path: Path) -> None:
        # Regression: an IMG_ filename was always keyed by its digits, the iOS
        # way, so a Canon or Android IMG_1234.JPG in a std source never matched.
        gallery = make_gallery(tmp_path)
        img_id = _setup_std_album_with_image(gallery, "2024-07-14 - Trip", "IMG_1234")

        result = resolve_entries((_entry("IMG_1234.JPG"),), scan_gallery(gallery))
        assert result.success
        assert result.members.images == (img_id,)

    def test_std_stem_does_not_match_ios_number(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _setup_std_album_with_image(gallery, "2024-07-14 - Trip", "0001")

        result = resolve_entries((_entry("IMG_0001.JPG"),), scan_gallery(gallery))
        assert [e.kind for e in result.errors] == [ResolutionErrorKind.NOT_FOUND]


class TestResolveMixed:
    def test_resolve_mixed_entries(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, album_id, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")
        _, col_id = make_gallery_collection(gallery, "2024 - Best Of")

        result = resolve_entries(
            (
                _entry("2024-07-14 - Trip"),
                _entry(format_collection_external_id(col_id)),
                _entry(format_image_external_id(img_id)),
            ),
            scan_gallery(gallery),
        )
        assert result.success
        assert result.members.albums == (album_id,)
        assert result.members.collections == (col_id,)
        assert result.members.images == (img_id,)


class TestResolveErrors:
    def test_unresolved_entry(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)

        result = resolve_entries((_entry("nonexistent"),), scan_gallery(gallery))
        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].kind == ResolutionErrorKind.NOT_FOUND

    def test_unresolved_external_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        fake_id = format_album_external_id(generate_album_id())

        result = resolve_entries((_entry(fake_id),), scan_gallery(gallery))
        assert not result.success
        assert result.errors[0].kind == ResolutionErrorKind.NOT_FOUND

    def test_ambiguous_album_name(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        # Create two albums with the same dir name in different year buckets
        name = "2024-07-14 - Trip"
        album1 = gallery / "albums" / "2024" / name
        album2 = gallery / "albums" / "2025" / name
        write_file(album1 / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        (album1 / "main-img").mkdir(parents=True, exist_ok=True)
        (album1 / "main-jpg").mkdir(parents=True, exist_ok=True)
        save_album_metadata(album1, AlbumMetadata(id=generate_album_id()))
        write_file(album2 / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        (album2 / "main-img").mkdir(parents=True, exist_ok=True)
        (album2 / "main-jpg").mkdir(parents=True, exist_ok=True)
        save_album_metadata(album2, AlbumMetadata(id=generate_album_id()))

        result = resolve_entries((_entry(name),), scan_gallery(gallery))
        assert not result.success
        assert result.errors[0].kind == ResolutionErrorKind.AMBIGUOUS

    def test_same_filename_with_two_date_hints_resolves_both(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path)
        img_ids = [
            _setup_album_with_media(gallery, name)[2]
            for name in ("2019-03-01 - Old Trip", "2024-08-10 - New Trip")
        ]

        result = resolve_entries(
            (
                _entry("IMG_0001.HEIC", date_hint=datetime(2019, 3, 1)),
                _entry("IMG_0001.HEIC", date_hint=datetime(2024, 8, 10)),
            ),
            scan_gallery(gallery),
        )

        assert result.success
        assert result.members.images == tuple(img_ids)

    def test_errors_carry_the_date_hint_of_their_entry(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _setup_album_with_media(gallery, "2019-03-01 - Old Trip")

        result = resolve_entries(
            (
                _entry("IMG_0001.HEIC", date_hint=datetime(2019, 3, 1)),
                _entry("IMG_0009.HEIC", date_hint=datetime(2024, 8, 10)),
            ),
            scan_gallery(gallery),
        )

        assert [(e.entry, e.kind, e.date_hint) for e in result.errors] == [
            ("IMG_0009.HEIC", ResolutionErrorKind.NOT_FOUND, datetime(2024, 8, 10)),
        ]

    def test_duplicate_entry(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")
        ext_id = format_album_external_id(album_id)

        # Same album referenced twice (by name and by ID)
        result = resolve_entries(
            (_entry("2024-07-14 - Trip"), _entry(ext_id)),
            scan_gallery(gallery),
        )
        assert not result.success
        assert [(e.kind, e.duplicate_of) for e in result.errors] == [
            (ResolutionErrorKind.DUPLICATE, "2024-07-14 - Trip"),
        ]

    def test_same_album_by_external_id_and_uuid_is_duplicate(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path)
        _, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")
        ext_id = format_album_external_id(album_id)

        result = resolve_entries(
            (_entry(ext_id), _entry(album_id)),
            scan_gallery(gallery),
        )

        assert result.members.albums == (album_id,)
        assert [(e.entry, e.kind, e.duplicate_of) for e in result.errors] == [
            (album_id, ResolutionErrorKind.DUPLICATE, ext_id),
        ]

    def test_same_image_key_twice_is_duplicate(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, _, img_id, _ = _setup_album_with_media(gallery, "2024-07-14 - Trip")

        result = resolve_entries(
            (_entry("IMG_0001.HEIC"), _entry("IMG_0001.JPG")),
            scan_gallery(gallery),
        )

        assert result.members.images == (img_id,)
        assert [(e.entry, e.kind, e.duplicate_of) for e in result.errors] == [
            ("IMG_0001.JPG", ResolutionErrorKind.DUPLICATE, "IMG_0001.HEIC"),
        ]

    def test_image_and_video_sharing_a_key_both_resolve(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        album_dir, _ = make_gallery_album(gallery, "2024-07-14 - Trip")
        img_id = generate_media_id()
        vid_id = generate_media_id()
        save_media_metadata(
            album_dir,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(
                        images={img_id: "0003"},
                        videos={vid_id: "0003"},
                    ),
                },
            ),
        )

        result = resolve_entries(
            (_entry("IMG_0003.HEIC"), _entry("IMG_0003.MOV")),
            scan_gallery(gallery),
        )

        assert result.success
        assert result.members.images == (img_id,)
        assert result.members.videos == (vid_id,)


class TestScanGalleryUnreadable:
    def test_corrupt_album_is_listed_not_raised(self, tmp_path: Path) -> None:
        # Regression: one corrupt album.yaml stopped every collection import.
        gallery = make_gallery(tmp_path)
        broken, _ = make_gallery_album(gallery, "2024-07-01 - Broken")
        (broken / ".photree" / "album.yaml").write_text("- nope\n", encoding="utf-8")
        _, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")

        index = scan_gallery(gallery)
        result = resolve_entries((_entry("2024-07-14 - Trip"),), index)

        assert result.members.albums == (album_id,)
        assert index.unreadable_albums == (broken,)

    def test_corrupt_media_ids_keep_the_album(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        album_dir, album_id = make_gallery_album(gallery, "2024-07-14 - Trip")
        write_file(album_dir / ".photree" / "media-ids" / "main.yaml", "- nope\n")

        index = scan_gallery(gallery)

        assert [a.album_id for a in index.albums] == [album_id]
        assert index.unreadable_albums == (album_dir,)

    def test_corrupt_collection_is_listed(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        col_dir, _ = make_gallery_collection(gallery, "2024 - Best Of")
        (col_dir / ".photree" / "collection.yaml").write_text(
            "- nope\n",
            encoding="utf-8",
        )

        index = scan_gallery(gallery)

        assert index.collections == ()
        assert index.unreadable_collections == (col_dir,)
