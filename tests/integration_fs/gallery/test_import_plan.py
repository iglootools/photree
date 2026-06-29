"""Tests for photree.gallery.import_plan."""

from __future__ import annotations

from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.gallery import AlbumIndex
from photree.gallery.import_plan import (
    ImportAction,
    plan_imports,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_source(
    base: Path, name: str, *, album_id: str | None = None, media: bool = True
) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    if media:
        _write(d / "ios-main/orig-img/IMG_0001.HEIC")
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
            tmp_path / "src", "2024-07-14 - Hiking", album_id=album_id
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
            tmp_path / "src", "2024-07-14 - Hiking", album_id=generate_album_id()
        )
        # A *different* album already occupies the target name.
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        target.mkdir(parents=True)
        save_album_metadata(target, AlbumMetadata(id=generate_album_id()))

        result = plan_imports([source], _empty_index(), gallery, reimport=True)

        assert result.has_errors
        assert result.clobber_conflicts
        # No plan is produced for a clobber conflict.
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
