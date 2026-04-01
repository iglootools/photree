"""Tests for gallery-level operations: album ID indexing and rename planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.fs import (
    AlbumMetadata,
    format_album_external_id,
    generate_album_id,
    save_album_metadata,
)
from photree.gallery import (
    MissingAlbumIdError,
    build_album_id_to_path_index,
    build_album_index,
    plan_renames_from_csv,
    resolve_album_path_by_id,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _mark_album(album_dir: Path, album_id: str | None = None) -> str:
    """Create .photree/album.yaml with a generated (or given) ID. Returns the ID."""
    aid = album_id if album_id is not None else generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return aid


def _setup_media_source(album_dir: Path) -> None:
    """Create a minimal iOS media source so the album is detected."""
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


def _setup_album(
    base_dir: Path, name: str, album_id: str | None = None
) -> tuple[Path, str]:
    """Create a complete album directory. Returns (path, album_id)."""
    album_dir = base_dir / name
    _setup_media_source(album_dir)
    aid = _mark_album(album_dir, album_id)
    return (album_dir, aid)


# ---------------------------------------------------------------------------
# TestBuildAlbumIdToPathIndex
# ---------------------------------------------------------------------------


class TestBuildAlbumIdToPathIndex:
    def test_empty_gallery(self, tmp_path: Path) -> None:
        index = build_album_id_to_path_index(tmp_path)
        assert index.id_to_path == {}
        assert index.duplicates == {}

    def test_single_album(self, tmp_path: Path) -> None:
        album_dir, aid = _setup_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_id_to_path_index(tmp_path)
        assert index.id_to_path == {aid: album_dir}
        assert index.duplicates == {}

    def test_multiple_albums(self, tmp_path: Path) -> None:
        _, aid1 = _setup_album(tmp_path, "2024-06-15 - Trip")
        _, aid2 = _setup_album(tmp_path, "2024-07-20 - Vacation")
        index = build_album_id_to_path_index(tmp_path)
        assert len(index.id_to_path) == 2
        assert aid1 in index.id_to_path
        assert aid2 in index.id_to_path
        assert index.duplicates == {}

    def test_album_without_metadata_raises(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "2024-06-15 - No ID"
        _setup_media_source(album_dir)
        # Create .photree dir but no album.yaml — this is a legacy album,
        # not detected by discover_albums. So we need album.yaml without an ID.
        # Actually, discover_albums requires .photree/album.yaml to exist.
        # A directory with media but no album.yaml won't be discovered.
        # The scenario is: album.yaml exists but somehow has no valid content.
        # Let's create a proper album alongside a broken one.
        _setup_album(tmp_path, "2024-06-15 - Good Album")

        # Create album with empty album.yaml (load_album_metadata returns None)
        broken = tmp_path / "2024-07-01 - Broken"
        _setup_media_source(broken)
        photree_dir = broken / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        with pytest.raises(MissingAlbumIdError) as exc_info:
            build_album_id_to_path_index(tmp_path)
        assert broken in exc_info.value.albums

    def test_duplicate_ids_detected(self, tmp_path: Path) -> None:
        shared_id = generate_album_id()
        dir1, _ = _setup_album(tmp_path, "2024-06-15 - A", album_id=shared_id)
        dir2, _ = _setup_album(tmp_path, "2024-06-16 - B", album_id=shared_id)
        index = build_album_id_to_path_index(tmp_path)
        assert shared_id in index.duplicates
        assert set(index.duplicates[shared_id]) == {dir1, dir2}
        # id_to_path still has one entry (first occurrence)
        assert shared_id in index.id_to_path

    def test_nested_album_directories(self, tmp_path: Path) -> None:
        year_dir = tmp_path / "albums" / "2024"
        year_dir.mkdir(parents=True)
        _, aid = _setup_album(year_dir, "2024-06-15 - Nested")
        index = build_album_id_to_path_index(tmp_path)
        assert aid in index.id_to_path


# ---------------------------------------------------------------------------
# TestBuildAlbumIndex
# ---------------------------------------------------------------------------


class TestBuildAlbumIndex:
    def test_empty_list(self) -> None:
        index = build_album_index([])
        assert index.id_to_path == {}
        assert index.duplicates == {}

    def test_builds_index_from_list(self, tmp_path: Path) -> None:
        dir1, aid1 = _setup_album(tmp_path, "2024-06-15 - Trip")
        dir2, aid2 = _setup_album(tmp_path, "2024-07-20 - Vacation")
        index = build_album_index([dir1, dir2])
        assert index.id_to_path == {aid1: dir1, aid2: dir2}
        assert index.duplicates == {}

    def test_missing_metadata_raises(self, tmp_path: Path) -> None:
        good_dir, _ = _setup_album(tmp_path, "2024-06-15 - Good")
        broken = tmp_path / "2024-07-01 - Broken"
        _setup_media_source(broken)
        photree_dir = broken / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        with pytest.raises(MissingAlbumIdError) as exc_info:
            build_album_index([good_dir, broken])
        assert broken in exc_info.value.albums

    def test_duplicate_ids_detected(self, tmp_path: Path) -> None:
        shared_id = generate_album_id()
        dir1, _ = _setup_album(tmp_path, "2024-06-15 - A", album_id=shared_id)
        dir2, _ = _setup_album(tmp_path, "2024-06-16 - B", album_id=shared_id)
        index = build_album_index([dir1, dir2])
        assert shared_id in index.duplicates
        assert set(index.duplicates[shared_id]) == {dir1, dir2}


# ---------------------------------------------------------------------------
# TestResolveAlbumPathById
# ---------------------------------------------------------------------------


class TestResolveAlbumPathById:
    def test_found(self, tmp_path: Path) -> None:
        index = {
            "id-1": tmp_path / "album-a",
            "id-2": tmp_path / "album-b",
        }
        assert resolve_album_path_by_id(index, "id-1") == tmp_path / "album-a"

    def test_not_found_raises(self) -> None:
        index: dict[str, Path] = {"id-1": Path("/a")}
        with pytest.raises(KeyError, match="not found"):
            resolve_album_path_by_id(index, "id-missing")


# ---------------------------------------------------------------------------
# TestPlanRenamesFromCsv
# ---------------------------------------------------------------------------


class TestPlanRenamesFromCsv:
    def _make_index(
        self, tmp_path: Path, albums: list[tuple[str, str]]
    ) -> dict[str, Path]:
        """Build a simple index from (album_id, album_name) pairs."""
        return {aid: tmp_path / name for aid, name in albums}

    def test_no_changes(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - Summer Trip"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {"id": ext_id, "series": "", "title": "Summer Trip", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert errors == ()

    def test_title_change(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - Old Title"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {"id": ext_id, "series": "", "title": "New Title", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert len(actions) == 1
        assert actions[0].current_name == "2024-06-15 - Old Title"
        assert actions[0].new_name == "2024-06-15 - New Title"

    def test_series_change(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - Old Series - Trip"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {"id": ext_id, "series": "New Series", "title": "Trip", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert len(actions) == 1
        assert actions[0].new_name == "2024-06-15 - New Series - Trip"

    def test_location_change(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - Trip"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {"id": ext_id, "series": "", "title": "Trip", "location": "Hawaii"},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert len(actions) == 1
        assert actions[0].new_name == "2024-06-15 - Trip @ Hawaii"

    def test_multiple_field_changes(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - Vacation - Beach Day @ LA"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {
                "id": ext_id,
                "series": "Road Trip",
                "title": "Mountain Day",
                "location": "Denver",
            },
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert len(actions) == 1
        assert actions[0].new_name == "2024-06-15 - Road Trip - Mountain Day @ Denver"

    def test_preserves_immutable_fields(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - 02 - Series - Title @ Place [private]"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {
                "id": ext_id,
                "series": "New Series",
                "title": "New Title",
                "location": "New Place",
            },
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert len(actions) == 1
        # date=2024-06-15, part=02, private=True are preserved from disk
        assert actions[0].new_name == (
            "2024-06-15 - 02 - New Series - New Title @ New Place [private]"
        )

    def test_unknown_album_id_error(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        ext_id = format_album_external_id(aid)
        rows = [
            {"id": ext_id, "series": "", "title": "Trip", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, {})
        assert actions == ()
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_invalid_album_id_format_error(self) -> None:
        rows = [
            {"id": "not_a_valid_id", "series": "", "title": "Trip", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, {})
        assert actions == ()
        assert len(errors) == 1
        assert "Invalid album ID format" in errors[0]

    def test_empty_album_id_error(self) -> None:
        rows = [
            {"id": "", "series": "", "title": "Trip", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, {})
        assert actions == ()
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_empty_title_error(self, tmp_path: Path) -> None:
        aid = generate_album_id()
        album_dir = tmp_path / "2024-06-15 - Trip"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        rows = [
            {"id": ext_id, "series": "", "title": "", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert len(errors) == 1
        assert "title" in errors[0].lower()

    def test_nfc_normalization_no_spurious_change(self, tmp_path: Path) -> None:
        import unicodedata

        aid = generate_album_id()
        # Use NFC form on disk
        nfc_title = unicodedata.normalize("NFC", "Caf\u00e9")
        album_dir = tmp_path / f"2024-06-15 - {nfc_title}"
        album_dir.mkdir()
        index = {aid: album_dir}
        ext_id = format_album_external_id(aid)

        # CSV has NFD form of the same string
        nfd_title = unicodedata.normalize("NFD", "Caf\u00e9")
        rows = [
            {"id": ext_id, "series": "", "title": nfd_title, "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        # No rename because NFC comparison treats them as equal
        assert actions == ()

    def test_multiple_rows_mixed_results(self, tmp_path: Path) -> None:
        aid1 = generate_album_id()
        aid2 = generate_album_id()
        dir1 = tmp_path / "2024-06-15 - Trip A"
        dir2 = tmp_path / "2024-07-01 - Trip B"
        dir1.mkdir()
        dir2.mkdir()
        index = {aid1: dir1, aid2: dir2}

        rows = [
            # Changed
            {
                "id": format_album_external_id(aid1),
                "series": "",
                "title": "Trip A Updated",
                "location": "",
            },
            # Unchanged
            {
                "id": format_album_external_id(aid2),
                "series": "",
                "title": "Trip B",
                "location": "",
            },
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert len(actions) == 1
        assert actions[0].new_name == "2024-06-15 - Trip A Updated"
