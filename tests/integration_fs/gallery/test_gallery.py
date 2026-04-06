"""Tests for gallery-level operations: album ID indexing and rename planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.album.store.metadata import save_album_metadata
from photree.album.id import format_album_external_id, generate_album_id
from photree.album.store.protocol import AlbumMetadata
from photree.albums.index import (
    MissingAlbumIdError,
    build_album_index,
    resolve_album_path_by_id,
)
from photree.albums.renamer import plan_renames_from_csv
from photree.gallery.index import build_album_id_to_path_index


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


def _albums_dir(gallery: Path) -> Path:
    """Return the albums/ subdirectory, creating it if needed."""
    d = gallery / "albums"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# TestBuildAlbumIdToPathIndex
# ---------------------------------------------------------------------------


class TestBuildAlbumIdToPathIndex:
    def test_empty_gallery(self, tmp_path: Path) -> None:
        index = build_album_id_to_path_index(tmp_path)
        assert index.id_to_path == {}
        assert index.duplicates == {}

    def test_single_album(self, tmp_path: Path) -> None:
        album_dir, aid = _setup_album(_albums_dir(tmp_path), "2024-06-15 - Trip")
        index = build_album_id_to_path_index(tmp_path)
        assert index.id_to_path == {aid: album_dir}
        assert index.duplicates == {}

    def test_multiple_albums(self, tmp_path: Path) -> None:
        albums = _albums_dir(tmp_path)
        _, aid1 = _setup_album(albums, "2024-06-15 - Trip")
        _, aid2 = _setup_album(albums, "2024-07-20 - Vacation")
        index = build_album_id_to_path_index(tmp_path)
        assert len(index.id_to_path) == 2
        assert aid1 in index.id_to_path
        assert aid2 in index.id_to_path
        assert index.duplicates == {}

    def test_album_without_metadata_raises(self, tmp_path: Path) -> None:
        albums = _albums_dir(tmp_path)
        _setup_album(albums, "2024-06-15 - Good Album")

        # Create album with empty album.yaml (load_album_metadata returns None)
        broken = albums / "2024-07-01 - Broken"
        _setup_media_source(broken)
        photree_dir = broken / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        with pytest.raises(MissingAlbumIdError) as exc_info:
            build_album_id_to_path_index(tmp_path)
        assert broken in exc_info.value.albums

    def test_duplicate_ids_detected(self, tmp_path: Path) -> None:
        albums = _albums_dir(tmp_path)
        shared_id = generate_album_id()
        dir1, _ = _setup_album(albums, "2024-06-15 - A", album_id=shared_id)
        dir2, _ = _setup_album(albums, "2024-06-16 - B", album_id=shared_id)
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


# ---------------------------------------------------------------------------
# TestResolveAlbumPathById
# ---------------------------------------------------------------------------


class TestResolveAlbumPathById:
    def test_resolves_by_internal_id_from_external(self, tmp_path: Path) -> None:
        """External ID → parse to internal → resolve."""
        from photree.album.id import ALBUM_ID_PREFIX, parse_external_id

        dir1, aid1 = _setup_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_index([dir1])
        external_id = format_album_external_id(aid1)
        internal_id = parse_external_id(external_id, ALBUM_ID_PREFIX)
        assert resolve_album_path_by_id(index.id_to_path, internal_id) == dir1

    def test_resolves_by_internal_id(self, tmp_path: Path) -> None:
        dir1, aid1 = _setup_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_index([dir1])
        assert resolve_album_path_by_id(index.id_to_path, aid1) == dir1

    def test_raises_for_unknown_id(self, tmp_path: Path) -> None:
        dir1, _ = _setup_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_index([dir1])
        unknown = format_album_external_id(generate_album_id())
        with pytest.raises(KeyError, match="not found"):
            resolve_album_path_by_id(index.id_to_path, unknown)


# ---------------------------------------------------------------------------
# TestPlanRenamesFromCsv
# ---------------------------------------------------------------------------


class TestPlanRenamesFromCsv:
    def _make_index(self, tmp_path: Path) -> dict[str, Path]:
        dir1, aid1 = _setup_album(tmp_path, "2024-06-15 - Trip to Paris")
        dir2, aid2 = _setup_album(tmp_path, "2024-07-20 - Beach Vacation")
        return {aid1: dir1, aid2: dir2}

    def test_plans_rename_when_title_changes(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        aid = next(iter(index))
        ext_id = format_album_external_id(aid)
        rows = [{"id": ext_id, "series": "", "title": "New Title", "location": ""}]
        actions, errors = plan_renames_from_csv(rows, index)
        assert len(actions) == 1
        assert "New Title" in actions[0].new_name
        assert errors == ()

    def test_no_change_returns_no_action(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        aid = next(iter(index))
        ext_id = format_album_external_id(aid)
        rows = [
            {
                "id": ext_id,
                "series": "",
                "title": "Trip to Paris",
                "location": "",
            }
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert errors == ()

    def test_adds_series_to_name(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        aid = next(iter(index))
        ext_id = format_album_external_id(aid)
        rows = [
            {
                "id": ext_id,
                "series": "Europe",
                "title": "Trip to Paris",
                "location": "",
            }
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert len(actions) == 1
        assert "Europe" in actions[0].new_name
        assert errors == ()

    def test_invalid_album_id_format_error(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        rows = [{"id": "invalid", "series": "", "title": "X", "location": ""}]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert len(errors) == 1

    def test_empty_album_id_error(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        rows = [{"id": "", "series": "", "title": "X", "location": ""}]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert len(errors) == 1

    def test_empty_title_error(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        aid = next(iter(index))
        ext_id = format_album_external_id(aid)
        rows = [{"id": ext_id, "series": "", "title": "", "location": ""}]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert len(errors) == 1

    def test_nfc_normalization_no_spurious_change(self, tmp_path: Path) -> None:
        """NFC-equivalent strings should not trigger a rename."""
        import unicodedata

        index = self._make_index(tmp_path)
        aid = next(iter(index))
        ext_id = format_album_external_id(aid)
        # Get the current title and convert to NFC (should be identity)
        current_name = index[aid].name
        from photree.album.naming import parse_album_name

        parsed = parse_album_name(current_name)
        assert parsed is not None
        nfc_title = unicodedata.normalize("NFC", parsed.title)
        rows = [
            {
                "id": ext_id,
                "series": "",
                "title": nfc_title,
                "location": "",
            }
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert errors == ()

    def test_multiple_rows_mixed_results(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        aids = list(index.keys())
        ext1 = format_album_external_id(aids[0])
        ext2 = format_album_external_id(aids[1])
        rows = [
            {"id": ext1, "series": "", "title": "New Title 1", "location": ""},
            {"id": ext2, "series": "", "title": "Beach Vacation", "location": ""},
            {"id": "bad_id", "series": "", "title": "X", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert len(actions) == 1  # only first row changed
        assert len(errors) == 1  # bad_id error
