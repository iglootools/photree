import shutil
from pathlib import Path

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
from photree.foundation.layout import COLLECTIONS_DIR
from tests.testkit import make_gallery, make_gallery_album, write_file


def _load_metadata(collection_dir: Path) -> CollectionMetadata:
    metadata = load_collection_metadata(collection_dir)
    assert metadata is not None
    return metadata


def _explicit_collection(gallery: Path, name: str, album_ids: list[str]) -> Path:
    col_dir = gallery / COLLECTIONS_DIR / name[:4] / name
    col_dir.mkdir(parents=True)
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
            albums=album_ids,
        ),
    )
    return col_dir


class TestImplicitCollectionDetection:
    def test_creates_collection_from_album_series(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Canada Trip - Hiking")
        make_gallery_album(gallery, "2024-07-15 - 02 - Canada Trip - Kayaking")

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
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        make_gallery_album(gallery, "2024-07-16 - 02 - Trip - Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert any("2024-07-14--2024-07-16" in name for name in result.created)

    def test_same_date_series(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Morning")
        make_gallery_album(gallery, "2024-07-14 - 02 - Trip - Evening")

        result = refresh_collections(gallery)
        assert result.success
        assert any("2024-07-14 - Trip" in name for name in result.created)

    def test_non_contiguous_series_creates_separate_collections(
        self,
        tmp_path: Path,
    ) -> None:
        """Same series interrupted by another album → two collections."""
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        make_gallery_album(gallery, "2024-07-15 - Beach Day")  # interrupts
        make_gallery_album(gallery, "2024-07-16 - 02 - Trip - Day 2")

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
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        make_gallery_album(gallery, "2024-07-15 - 02 - Trip - Day 2")
        make_gallery_album(gallery, "2024-07-16 - 03 - Trip - Day 3")

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
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - Just Hiking")
        make_gallery_album(gallery, "2024-07-15 - Beach Day")

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.created) == 0

    def test_deletes_orphaned_implicit_collection(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
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

        # Finder's metadata does not keep the directory alive.
        write_file(col_dir / ".DS_Store")

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.deleted) == 1
        assert result.kept_directories == ()
        assert not col_dir.exists()

    def test_orphaned_collection_keeps_user_files(self, tmp_path: Path) -> None:
        """Regression: the orphan was removed with rmtree, user files and all."""
        gallery = make_gallery(tmp_path)
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
        write_file(col_dir / "notes.txt", "keep me")

        result = refresh_collections(gallery)

        assert result.deleted == ("2024-07-14 - Old Trip",)
        assert result.kept_directories == ("2024-07-14 - Old Trip",)
        assert [p.name for p in col_dir.iterdir()] == ["notes.txt"]
        assert discover_collections(gallery) == []

    def test_adding_album_preserves_collection_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Day 1")

        refresh_collections(gallery)
        collections = discover_collections(gallery)
        assert len(collections) == 1
        original_id = _load_metadata(collections[0]).id

        # Add another album with same series (extends date range)
        _, aid2 = make_gallery_album(gallery, "2024-07-15 - 02 - Trip - Day 2")

        result = refresh_collections(gallery)
        assert result.success

        collections = discover_collections(gallery)
        assert len(collections) == 1
        meta = load_collection_metadata(collections[0])
        assert meta is not None
        assert sorted(meta.albums) == sorted([aid1, aid2])
        assert meta.id == original_id

    def test_removing_album_preserves_collection_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Day 1")
        album2, _aid2 = make_gallery_album(gallery, "2024-07-15 - 02 - Trip - Day 2")

        refresh_collections(gallery)
        collections = discover_collections(gallery)
        assert len(collections) == 1
        original_id = _load_metadata(collections[0]).id

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
        gallery = make_gallery(tmp_path)
        _, _aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Old Name - Day 1")
        _, _aid2 = make_gallery_album(gallery, "2024-07-15 - 02 - Old Name - Day 2")

        refresh_collections(gallery)
        collections = discover_collections(gallery)
        assert len(collections) == 1
        old_id = _load_metadata(collections[0]).id

        album1 = gallery / "albums" / "2024" / "2024-07-14 - 01 - Old Name - Day 1"
        album2 = gallery / "albums" / "2024" / "2024-07-15 - 02 - Old Name - Day 2"
        album1.rename(album1.parent / "2024-07-14 - 01 - New Name - Day 1")
        album2.rename(album2.parent / "2024-07-15 - 02 - New Name - Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert len(result.renamed) == 1

        collections = discover_collections(gallery)
        assert len(collections) == 1
        meta = _load_metadata(collections[0])
        assert meta.id == old_id

    def test_divergent_series_creates_new_and_keeps_old(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Original - Day 1")
        album2, aid2 = make_gallery_album(gallery, "2024-07-15 - 02 - Original - Day 2")

        refresh_collections(gallery)
        [original] = discover_collections(gallery)
        original_id = _load_metadata(original).id

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
            col.name: _load_metadata(col) for col in discover_collections(gallery)
        }
        assert by_name.keys() == {"2024-07-14 - Original", "2024-07-15 - Other"}
        assert by_name["2024-07-14 - Original"].id == original_id
        assert by_name["2024-07-14 - Original"].albums == [aid1]
        assert by_name["2024-07-15 - Other"].albums == [aid2]

    def test_album_dropping_series_leaves_collection(self, tmp_path: Path) -> None:
        """Regression: the refresh renamed the album back into the series."""
        gallery = make_gallery(tmp_path)
        _, aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Original - Day 1")
        album2, _ = make_gallery_album(gallery, "2024-07-15 - 02 - Original - Day 2")

        refresh_collections(gallery)

        album2.rename(album2.parent / "2024-07-15 - Just Day 2")

        result = refresh_collections(gallery)
        assert result.success
        assert result.album_renames == ()
        assert result.renamed == (
            ("2024-07-14--2024-07-15 - Original", "2024-07-14 - Original"),
        )
        assert (album2.parent / "2024-07-15 - Just Day 2").is_dir()

        [collection] = discover_collections(gallery)
        assert _load_metadata(collection).albums == [aid1]


class TestSmartCollectionRefresh:
    def test_materializes_albums_by_date_range(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid1 = make_gallery_album(gallery, "2024-07-14 - Trip A")
        _, aid2 = make_gallery_album(gallery, "2024-07-15 - Trip B")
        make_gallery_album(gallery, "2024-08-01 - Unrelated")

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
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - Trip")

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
    def test_removes_series_from_explicit_collection_members(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path)
        _, aid = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        _explicit_collection(gallery, "2024-07-14 - Trip", [aid])

        result = refresh_collections(gallery)
        assert result.success
        assert result.album_renames == (
            ("2024-07-14 - 01 - Trip - Hiking", "2024-07-14 - 01 - Hiking"),
        )

    def test_keeps_series_of_albums_outside_explicit_collection(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: any explicit collection stripped its title gallery-wide."""
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        _explicit_collection(gallery, "2019 - Trip", [])

        result = refresh_collections(gallery)
        assert result.success
        assert result.album_renames == ()
        assert result.created == ("2024-07-14 - Trip",)

    def test_adds_series_when_implicit_collection_contains_album(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path)
        _, aid = make_gallery_album(gallery, "2024-07-14 - Hiking")

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

    def test_lifecycle_round_trip_strips_then_restores_series(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path)
        album1, aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        album2, aid2 = make_gallery_album(gallery, "2024-07-15 - 02 - Trip - Kayaking")
        refresh_collections(gallery)
        [col_dir] = discover_collections(gallery)
        implicit = _load_metadata(col_dir)

        save_collection_metadata(
            col_dir,
            implicit.model_copy(
                update={
                    "members": CollectionMembers.MANUAL,
                    "lifecycle": CollectionLifecycle.EXPLICIT,
                    "strategy": CollectionStrategy.IMPORT,
                },
            ),
        )
        stripped = refresh_collections(gallery)
        assert stripped.album_renames == (
            (album1.name, "2024-07-14 - 01 - Hiking"),
            (album2.name, "2024-07-15 - 02 - Kayaking"),
        )

        save_collection_metadata(col_dir, implicit)
        restored = refresh_collections(gallery)
        assert restored.success
        assert restored.album_renames == (
            ("2024-07-14 - 01 - Hiking", album1.name),
            ("2024-07-15 - 02 - Kayaking", album2.name),
        )
        assert _load_metadata(col_dir) == implicit
        assert sorted(implicit.albums) == sorted([aid1, aid2])


class TestDryRun:
    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        make_gallery_album(gallery, "2024-07-15 - 02 - Trip - Kayaking")

        result = refresh_collections(gallery, dry_run=True)
        assert result.success
        assert len(result.created) == 1

        collections = discover_collections(gallery)
        assert len(collections) == 0


class TestDryRunMatchesRealRun:
    def test_dry_run_sees_title_sync_renames(self, tmp_path: Path) -> None:
        """Regression: the dry run re-scanned disk and saw the unstripped series."""
        gallery = make_gallery(tmp_path)
        _, aid1 = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        _, aid2 = make_gallery_album(gallery, "2024-07-15 - 02 - Trip - Kayaking")
        _explicit_collection(gallery, "2024-07 - Trip", [aid1, aid2])

        dry = refresh_collections(gallery, dry_run=True)

        assert dry.success
        assert len(dry.album_renames) == 2
        # The explicit collection owns the series: no implicit one is planned.
        assert dry.created == ()

        real = refresh_collections(gallery)
        assert real.album_renames == dry.album_renames
        assert real.created == dry.created

    def test_dry_run_smart_stage_sees_planned_collections(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the smart stage re-read the disk, which a dry run left as is."""
        gallery = make_gallery(tmp_path)
        album, _ = make_gallery_album(gallery, "2024-07-14 - Hiking")
        july = gallery / COLLECTIONS_DIR / "2024" / "2024-07 - July"
        july.mkdir(parents=True)
        save_collection_metadata(
            july,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.EXPLICIT,
                strategy=CollectionStrategy.DATE_RANGE,
            ),
        )
        refresh_collections(gallery)
        # The new series creates an implicit collection inside July's range.
        album.rename(album.parent / "2024-07-14 - 01 - Trip - Hiking")

        dry = refresh_collections(gallery, dry_run=True)
        real = refresh_collections(gallery)

        assert dry.updated == ("2024-07 - July",)
        assert real.updated == dry.updated


class TestRefreshErrors:
    def test_naming_issues_are_carried(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        album_dir, _ = make_gallery_album(gallery, "2024-07-14 -  Double Space")

        result = refresh_collections(gallery)

        [error] = result.errors
        assert error.kind is CollectionRefreshErrorKind.ALBUM_NAMING
        assert error.path == album_dir
        assert error.naming_issues

    def test_title_sync_onto_existing_album_is_reported(self, tmp_path: Path) -> None:
        """Regression: the rename raised an OSError traceback."""
        gallery = make_gallery(tmp_path)
        source, aid = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        occupied, _ = make_gallery_album(gallery, "2024-07-14 - 02 - Hiking")
        # Make the stripped name collide with an existing directory.
        stripped = source.parent / "2024-07-14 - 01 - Hiking"
        stripped.mkdir()
        _explicit_collection(gallery, "2024-07 - Trip", [aid])

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
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Morning")
        make_gallery_album(gallery, "2024-07-14 - 02 - Other - Noon")
        make_gallery_album(gallery, "2024-07-14 - 03 - Trip - Evening")

        result = refresh_collections(gallery)

        assert result.errors == (
            CollectionRefreshError(
                CollectionRefreshErrorKind.SERIES_NAME_CONFLICT,
                name="2024-07-14 - Trip",
            ),
        )
        # Nothing was written: conflicts are detected on the whole plan.
        assert discover_collections(gallery) == []

    def test_occupied_target_stops_the_whole_stage(self, tmp_path: Path) -> None:
        """Regression: earlier groups were created and orphans deleted anyway."""
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Alpha - Morning")
        make_gallery_album(gallery, "2024-07-16 - 01 - Beta - Morning")
        occupied = gallery / COLLECTIONS_DIR / "2024" / "2024-07-16 - Beta"
        occupied.mkdir(parents=True)
        orphan = gallery / COLLECTIONS_DIR / "2024" / "2024-06-01 - Gone"
        orphan.mkdir(parents=True)
        save_collection_metadata(
            orphan,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.IMPLICIT,
                strategy=CollectionStrategy.ALBUM_SERIES,
                albums=["nonexistent-id"],
            ),
        )

        result = refresh_collections(gallery)

        assert result.errors == (
            CollectionRefreshError(
                CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
                target=occupied,
            ),
        )
        assert result.created == ()
        assert discover_collections(gallery) == [orphan]

    def test_case_only_series_rename(self, tmp_path: Path) -> None:
        """Regression: the collection found itself in its way on APFS."""
        gallery = make_gallery(tmp_path)
        album1, _ = make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Morning")
        album2, _ = make_gallery_album(gallery, "2024-07-14 - 02 - Trip - Evening")
        refresh_collections(gallery)
        [before] = discover_collections(gallery)
        before_id = _load_metadata(before).id
        album1.rename(album1.parent / "2024-07-14 - 01 - trip - Morning")
        album2.rename(album2.parent / "2024-07-14 - 02 - trip - Evening")

        result = refresh_collections(gallery)

        assert result.success
        assert result.renamed == (("2024-07-14 - Trip", "2024-07-14 - trip"),)
        [after] = discover_collections(gallery)
        assert after.name == "2024-07-14 - trip"
        assert _load_metadata(after).id == before_id

    def test_uses_injected_collection_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        make_gallery_album(gallery, "2024-07-14 - 01 - Trip - Hiking")
        fixed_id = generate_collection_id()

        result = refresh_collections(gallery, new_id=lambda: fixed_id)

        assert result.success
        [col_dir] = discover_collections(gallery)
        meta = load_collection_metadata(col_dir)
        assert meta is not None
        assert meta.id == fixed_id
