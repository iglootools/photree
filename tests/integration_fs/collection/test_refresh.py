import shutil
from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.id import generate_collection_id
from photree.collection.refresh import refresh_collections
from photree.collection.refresh.result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
)
from photree.collection.store.collection_discovery import discover_collections
from photree.collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.layout import COLLECTIONS_DIR


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata())
    return gallery


def _setup_album(
    gallery: Path, name: str, album_id: str | None = None
) -> tuple[Path, str]:
    album_dir = gallery / "albums" / "2024" / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)
    aid = album_id or generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return album_dir, aid


class TestImplicitCollectionDetection:
    def test_creates_collection_from_album_series(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Canada Trip - Hiking")
        _setup_album(gallery, "2024-07-15 - 02 - Canada Trip - Kayaking")

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.created) == 1
        assert "Canada Trip" in result.created[0]

        collections = discover_collections(gallery)
        assert len(collections) == 1
        meta = load_collection_metadata(collections[0])
        assert meta is not None
        assert meta.lifecycle == CollectionLifecycle.IMPLICIT
        assert meta.members == CollectionMembers.SMART
        assert len(meta.albums) == 2

    def test_date_range_for_multiday_series(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        _setup_album(gallery, "2024-07-16 - 02 - Trip - Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert any("2024-07-14--2024-07-16" in name for name in result.created)

    def test_same_date_series(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Morning")
        _setup_album(gallery, "2024-07-14 - 02 - Trip - Evening")

        result = refresh_collections(gallery)
        assert result.success
        assert any("2024-07-14 - Trip" in name for name in result.created)

    def test_non_contiguous_series_creates_separate_collections(
        self, tmp_path: Path
    ) -> None:
        """Same series interrupted by another album → two collections."""
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        _setup_album(gallery, "2024-07-15 - Beach Day")  # interrupts
        _setup_album(gallery, "2024-07-16 - 02 - Trip - Day 2")

        result = refresh_collections(gallery)
        assert result.success
        trip_collections = [n for n in result.created if "Trip" in n]
        assert len(trip_collections) == 2

        collections = discover_collections(gallery)
        trip_cols = [c for c in collections if "Trip" in c.name]
        assert len(trip_cols) == 2
        for col_dir in trip_cols:
            meta = load_collection_metadata(col_dir)
            assert meta is not None
            assert len(meta.albums) == 1

    def test_contiguous_series_creates_single_collection(self, tmp_path: Path) -> None:
        """Same series with no interruption → one collection."""
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        _setup_album(gallery, "2024-07-15 - 02 - Trip - Day 2")
        _setup_album(gallery, "2024-07-16 - 03 - Trip - Day 3")

        result = refresh_collections(gallery)
        assert result.success
        trip_collections = [n for n in result.created if "Trip" in n]
        assert len(trip_collections) == 1

        collections = discover_collections(gallery)
        trip_cols = [c for c in collections if "Trip" in c.name]
        assert len(trip_cols) == 1
        meta = load_collection_metadata(trip_cols[0])
        assert meta is not None
        assert len(meta.albums) == 3

    def test_no_series_no_collection(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Just Hiking")
        _setup_album(gallery, "2024-07-15 - Beach Day")

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.created) == 0

    def test_deletes_orphaned_implicit_collection(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        # Create an implicit collection with no matching albums
        col_dir = gallery / COLLECTIONS_DIR / "2024" / "2024-07-14 - Old Trip"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.IMPLICIT,
                strategy=CollectionStrategy.ALBUM_SERIES,
                albums=["nonexistent-id"],
            ),
        )

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.deleted) == 1
        assert not col_dir.exists()

    def test_adding_album_preserves_collection_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid1 = _setup_album(gallery, "2024-07-14 - 01 - Trip - Day 1")

        refresh_collections(gallery)
        collections = discover_collections(gallery)
        assert len(collections) == 1
        original_id = load_collection_metadata(collections[0]).id

        # Add another album with same series (extends date range)
        _, aid2 = _setup_album(gallery, "2024-07-15 - 02 - Trip - Day 2")

        result = refresh_collections(gallery)
        assert result.success

        collections = discover_collections(gallery)
        assert len(collections) == 1
        meta = load_collection_metadata(collections[0])
        assert meta is not None
        assert sorted(meta.albums) == sorted([aid1, aid2])
        assert meta.id == original_id

    def test_removing_album_preserves_collection_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid1 = _setup_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        album2, _aid2 = _setup_album(gallery, "2024-07-15 - 02 - Trip - Day 2")

        refresh_collections(gallery)
        collections = discover_collections(gallery)
        assert len(collections) == 1
        original_id = load_collection_metadata(collections[0]).id

        shutil.rmtree(album2)

        result = refresh_collections(gallery)
        assert result.success

        collections = discover_collections(gallery)
        assert len(collections) == 1
        meta = load_collection_metadata(collections[0])
        assert meta is not None
        assert meta.albums == [aid1]
        assert meta.id == original_id


class TestImplicitCollectionRename:
    def test_renames_when_all_albums_change_series(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, _aid1 = _setup_album(gallery, "2024-07-14 - 01 - Old Name - Day 1")
        _, _aid2 = _setup_album(gallery, "2024-07-15 - 02 - Old Name - Day 2")

        refresh_collections(gallery)
        collections = discover_collections(gallery)
        assert len(collections) == 1
        old_id = load_collection_metadata(collections[0]).id

        album1 = gallery / "albums" / "2024" / "2024-07-14 - 01 - Old Name - Day 1"
        album2 = gallery / "albums" / "2024" / "2024-07-15 - 02 - Old Name - Day 2"
        album1.rename(album1.parent / "2024-07-14 - 01 - New Name - Day 1")
        album2.rename(album2.parent / "2024-07-15 - 02 - New Name - Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.renamed) == 1

        collections = discover_collections(gallery)
        assert len(collections) == 1
        meta = load_collection_metadata(collections[0])
        assert meta.id == old_id

    def test_divergent_series_creates_new_and_keeps_old(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid1 = _setup_album(gallery, "2024-07-14 - 01 - Original - Day 1")
        album2, aid2 = _setup_album(gallery, "2024-07-15 - 02 - Original - Day 2")

        refresh_collections(gallery)
        [original] = discover_collections(gallery)
        original_id = load_collection_metadata(original).id

        album2.rename(album2.parent / "2024-07-15 - 01 - Other - Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert result.created == ("2024-07-15 - Other",)
        assert result.deleted == ()
        # The date range in the name shrinks with the membership; the id does not
        # change, so references to the collection survive the split.
        assert result.renamed == (
            ("2024-07-14--2024-07-15 - Original", "2024-07-14 - Original"),
        )

        by_name = {
            col.name: load_collection_metadata(col)
            for col in discover_collections(gallery)
        }
        assert by_name.keys() == {"2024-07-14 - Original", "2024-07-15 - Other"}
        assert by_name["2024-07-14 - Original"].id == original_id
        assert by_name["2024-07-14 - Original"].albums == [aid1]
        assert by_name["2024-07-15 - Other"].albums == [aid2]

    def test_album_dropping_series_is_renamed_back(self, tmp_path: Path) -> None:
        """An implicit collection's membership outlives the album's name: dropping
        the series does not leave the collection, the refresh restores it."""
        gallery = _setup_gallery(tmp_path)
        _, aid1 = _setup_album(gallery, "2024-07-14 - 01 - Original - Day 1")
        album2, aid2 = _setup_album(gallery, "2024-07-15 - 02 - Original - Day 2")

        refresh_collections(gallery)

        album2.rename(album2.parent / "2024-07-15 - Just Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert result.album_renames == (
            ("2024-07-15 - Just Day 2", "2024-07-15 - Original - Just Day 2"),
        )
        assert result.created == ()
        assert result.deleted == ()
        assert (album2.parent / "2024-07-15 - Original - Just Day 2").is_dir()

        [collection] = discover_collections(gallery)
        assert load_collection_metadata(collection).albums == [aid1, aid2]


class TestSmartCollectionRefresh:
    def test_materializes_albums_by_date_range(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid1 = _setup_album(gallery, "2024-07-14 - Trip A")
        _, aid2 = _setup_album(gallery, "2024-07-15 - Trip B")
        _setup_album(gallery, "2024-08-01 - Unrelated")

        # Create a smart collection covering July
        col_dir = gallery / COLLECTIONS_DIR / "2024" / "2024-07 - July Adventures"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.EXPLICIT,
                strategy=CollectionStrategy.DATE_RANGE,
            ),
        )

        result = refresh_collections(gallery)
        assert result.success

        meta = load_collection_metadata(col_dir)
        assert meta is not None
        assert sorted(meta.albums) == sorted([aid1, aid2])

    def test_smart_includes_sub_collections(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Trip")

        # Create a sub-collection in range
        sub_dir = gallery / COLLECTIONS_DIR / "2024" / "2024-07-14 - Sub"
        sub_dir.mkdir(parents=True)
        sub_meta = CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        )
        save_collection_metadata(sub_dir, sub_meta)

        # Create a smart collection covering the same range
        smart_dir = gallery / COLLECTIONS_DIR / "2024" / "2024-07 - Parent"
        smart_dir.mkdir(parents=True)
        save_collection_metadata(
            smart_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.EXPLICIT,
                strategy=CollectionStrategy.DATE_RANGE,
            ),
        )

        refresh_collections(gallery)

        meta = load_collection_metadata(smart_dir)
        assert meta is not None
        assert sub_meta.id in meta.collections


class TestAlbumTitleSync:
    def test_removes_series_when_explicit_collection_exists(
        self, tmp_path: Path
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Hiking")

        # Create an explicit collection with matching title
        col_dir = gallery / COLLECTIONS_DIR / "2024" / "2024-07-14 - Trip"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
            ),
        )

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.album_renames) == 1
        old, new = result.album_renames[0]
        assert "Trip" in old
        assert "Trip" not in new

    def test_adds_series_when_implicit_collection_contains_album(
        self, tmp_path: Path
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        _, aid = _setup_album(gallery, "2024-07-14 - Hiking")

        # Create an implicit collection that contains this album
        col_dir = gallery / COLLECTIONS_DIR / "2024" / "2024-07-14 - Trip"
        col_dir.mkdir(parents=True)
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.IMPLICIT,
                strategy=CollectionStrategy.ALBUM_SERIES,
                albums=[aid],
            ),
        )

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.album_renames) == 1
        old, new = result.album_renames[0]
        assert "Trip" not in old
        assert "Trip" in new


class TestDryRun:
    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        _setup_album(gallery, "2024-07-15 - 02 - Trip - Kayaking")

        result = refresh_collections(gallery, dry_run=True)
        assert result.success
        assert len(result.created) == 1

        collections = discover_collections(gallery)
        assert len(collections) == 0


def _explicit_collection(gallery: Path, name: str) -> Path:
    col_dir = gallery / COLLECTIONS_DIR / "2024" / name
    col_dir.mkdir(parents=True)
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        ),
    )
    return col_dir


class TestDryRunMatchesRealRun:
    def test_dry_run_sees_title_sync_renames(self, tmp_path: Path) -> None:
        """Regression: the dry run re-scanned disk and saw the unstripped series."""
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        _setup_album(gallery, "2024-07-15 - 02 - Trip - Kayaking")
        _explicit_collection(gallery, "2024-07 - Trip")

        dry = refresh_collections(gallery, dry_run=True)

        assert dry.success
        assert len(dry.album_renames) == 2
        # The explicit collection owns the series: no implicit one is planned.
        assert dry.created == ()

        real = refresh_collections(gallery)
        assert real.album_renames == dry.album_renames
        assert real.created == dry.created


class TestRefreshErrors:
    def test_naming_issues_are_carried(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album_dir, _ = _setup_album(gallery, "2024-07-14 -  Double Space")

        result = refresh_collections(gallery)

        [error] = result.errors
        assert error.kind is CollectionRefreshErrorKind.ALBUM_NAMING
        assert error.path == album_dir
        assert error.naming_issues

    def test_title_sync_onto_existing_album_is_reported(self, tmp_path: Path) -> None:
        """Regression: the rename raised an OSError traceback."""
        gallery = _setup_gallery(tmp_path)
        source, _ = _setup_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        occupied, _ = _setup_album(gallery, "2024-07-14 - 02 - Hiking")
        # Make the stripped name collide with an existing directory.
        stripped = source.parent / "2024-07-14 - 01 - Hiking"
        stripped.mkdir()
        _explicit_collection(gallery, "2024-07 - Trip")

        result = refresh_collections(gallery)

        assert result.errors == (
            CollectionRefreshError(
                CollectionRefreshErrorKind.ALBUM_RENAME_CONFLICT,
                path=source,
                target=stripped,
            ),
        )
        assert source.is_dir()
        assert occupied.is_dir()

    def test_same_series_runs_on_same_date_conflict(self, tmp_path: Path) -> None:
        """Regression: series A, B, A on one date built one name twice."""
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Morning")
        _setup_album(gallery, "2024-07-14 - 02 - Other - Noon")
        _setup_album(gallery, "2024-07-14 - 03 - Trip - Evening")

        result = refresh_collections(gallery)

        assert result.errors == (
            CollectionRefreshError(
                CollectionRefreshErrorKind.SERIES_NAME_CONFLICT,
                name="2024-07-14 - Trip",
            ),
        )
        # Nothing was written: conflicts are detected on the whole plan.
        assert discover_collections(gallery) == []

    def test_uses_injected_collection_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        fixed_id = generate_collection_id()

        result = refresh_collections(gallery, new_id=lambda: fixed_id)

        assert result.success
        [col_dir] = discover_collections(gallery)
        meta = load_collection_metadata(col_dir)
        assert meta is not None and meta.id == fixed_id
