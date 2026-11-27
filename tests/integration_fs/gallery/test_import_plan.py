from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.index import AlbumIndex
from photree.gallery.import_plan import (
    ClobberConflict,
    ImportAction,
    InterruptedReimport,
    plan_imports,
)
from tests.testkit import write_file


def _make_source(
    base: Path,
    name: str,
    *,
    album_id: str | None = None,
    media: bool = True,
) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    if media:
        write_file(d / "ios-main/orig-img/IMG_0001.HEIC")
    if album_id is not None:
        save_album_metadata(d, AlbumMetadata(id=album_id))
    return d


def _empty_index() -> AlbumIndex:
    return AlbumIndex(id_to_path={}, duplicates={})


class TestPlanImportsActions:
    def test_new_album(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = plan_imports([source], _empty_index(), gallery, reimport=False)

        assert not result.has_errors
        assert result.plans[0].action is ImportAction.NEW

    def test_skip_when_target_exists(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")
        # Physically create the target directory.
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        target.mkdir(parents=True)

        result = plan_imports([source], _empty_index(), gallery, reimport=False)

        assert not result.has_errors
        assert result.plans[0].action is ImportAction.SKIP
        assert result.plans[0].existing == target

    def test_reimport_when_target_exists(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")
        (gallery / "albums" / "2024" / "2024-07-14 - Hiking").mkdir(parents=True)

        result = plan_imports([source], _empty_index(), gallery, reimport=True)

        assert not result.has_errors
        assert result.plans[0].action is ImportAction.REIMPORT

    def test_skip_when_id_in_gallery(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        album_id = generate_album_id()
        source = _make_source(
            tmp_path / "src",
            "2024-07-14 - Hiking",
            album_id=album_id,
        )
        existing = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        index = AlbumIndex(id_to_path={album_id: existing}, duplicates={})

        result = plan_imports([source], index, gallery, reimport=False)

        assert not result.has_errors
        plan = result.plans[0]
        assert plan.action is ImportAction.SKIP
        assert plan.existing == existing


class TestPlanImportsErrors:
    def test_naming_error(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        source = _make_source(tmp_path / "src", "no-date-here")

        result = plan_imports([source], _empty_index(), gallery, reimport=False)

        assert result.has_errors
        assert result.naming_errors

    def test_structure_error(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking", media=False)

        result = plan_imports([source], _empty_index(), gallery, reimport=False)

        assert result.has_errors
        assert source in result.structure_errors

    def test_clobber_conflict(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        source = _make_source(
            tmp_path / "src",
            "2024-07-14 - Hiking",
            album_id=generate_album_id(),
        )
        # A *different* album already occupies the target name.
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        target.mkdir(parents=True)
        save_album_metadata(target, AlbumMetadata(id=generate_album_id()))

        result = plan_imports([source], _empty_index(), gallery, reimport=True)

        assert result.has_errors
        assert result.clobber_conflicts
        assert not result.to_import

    def test_collision_within_batch(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        a = _make_source(tmp_path / "src", "2024-07-14 - Morning")
        b = _make_source(tmp_path / "src", "2024-07-14 - Evening")

        result = plan_imports([a, b], _empty_index(), gallery, reimport=False)

        assert result.has_errors
        assert result.date_collisions

    def test_collision_against_gallery(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        existing = gallery / "albums" / "2024" / "2024-07-14 - Existing"
        index = AlbumIndex(id_to_path={generate_album_id(): existing}, duplicates={})
        source = _make_source(tmp_path / "src", "2024-07-14 - New")

        result = plan_imports([source], index, gallery, reimport=False)

        assert result.has_errors
        assert result.date_collisions

    def test_no_collision_with_distinct_parts(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        a = _make_source(tmp_path / "src", "2024-07-14 - 01 - Morning")
        b = _make_source(tmp_path / "src", "2024-07-14 - 02 - Evening")

        result = plan_imports([a, b], _empty_index(), gallery, reimport=False)

        assert not result.has_errors
        assert all(p.action is ImportAction.NEW for p in result.plans)


class TestPlanImportsRenamedSource:
    def test_rename_onto_other_album_is_a_clobber_conflict(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the ID match short-circuited the clobber check."""
        gallery = tmp_path / "gallery"
        album_id = generate_album_id()
        existing = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        occupant_id = generate_album_id()
        occupied = gallery / "albums" / "2024" / "2024-07-14 - Hiking the Rockies"
        occupied.mkdir(parents=True)
        save_album_metadata(occupied, AlbumMetadata(id=occupant_id))
        source = _make_source(tmp_path / "src", occupied.name, album_id=album_id)
        index = AlbumIndex(
            id_to_path={album_id: existing, occupant_id: occupied},
            duplicates={},
        )

        result = plan_imports([source], index, gallery, reimport=True)

        assert result.clobber_conflicts == (
            ClobberConflict(
                source=source,
                existing=occupied,
                source_id=album_id,
                existing_id=occupant_id,
            ),
        )
        assert not result.to_import

    def test_rename_onto_free_name_is_a_reimport(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        album_id = generate_album_id()
        existing = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        source = _make_source(
            tmp_path / "src",
            "2024-07-14 - Hiking the Rockies",
            album_id=album_id,
        )
        index = AlbumIndex(id_to_path={album_id: existing}, duplicates={})

        result = plan_imports([source], index, gallery, reimport=True)

        assert not result.has_errors
        assert result.plans[0].action is ImportAction.REIMPORT
        assert result.plans[0].existing == existing


class TestPlanImportsInterruptedReimport:
    def test_album_hidden_by_an_interrupted_reimport_is_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the hidden album's source was planned as new."""
        gallery = tmp_path / "gallery"
        album_id = generate_album_id()
        backup = _make_source(
            gallery / "albums" / "2024",
            ".2024-07-14 - Hiking.old",
            album_id=album_id,
        )
        source = _make_source(
            tmp_path / "src",
            "2024-07-14 - Hiking",
            album_id=album_id,
        )

        result = plan_imports([source], _empty_index(), gallery, reimport=True)

        assert result.interrupted_reimports == (
            InterruptedReimport(
                backup=backup,
                album_dir=gallery / "albums" / "2024" / "2024-07-14 - Hiking",
                live=None,
            ),
        )
        assert result.has_errors

    def test_stale_copy_names_the_album_holding_its_id(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        album_id = generate_album_id()
        backup = _make_source(
            gallery / "albums" / "2024",
            ".2024-07-14 - Hiking.old",
            album_id=album_id,
        )
        live = gallery / "albums" / "2024" / "2024-07-14 - Hiking the Rockies"
        index = AlbumIndex(id_to_path={album_id: live}, duplicates={})
        source = _make_source(tmp_path / "src", "2024-08-01 - Beach")

        result = plan_imports([source], index, gallery, reimport=False)

        assert result.interrupted_reimports == (
            InterruptedReimport(
                backup=backup,
                album_dir=gallery / "albums" / "2024" / "2024-07-14 - Hiking",
                live=live,
            ),
        )
