import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from photree.album.id import (
    ALBUM_ID_PREFIX,
    format_album_external_id,
    generate_album_id,
    parse_external_id,
)
from photree.album.naming import parse_album_name
from photree.album.stats.testkit import ALBUMS_STATS
from photree.albums.index import (
    AlbumIdNotFoundError,
    build_album_index,
    resolve_album_path_by_id,
)
from photree.albums.renamer import RenamePlanErrorKind, plan_renames_from_csv
from photree.foundation.metadata_io import InvalidMetadataError
from photree.gallery.index import build_album_id_to_path_index
from photree.gallery.stats import compute_gallery_stats
from tests.testkit import add_ios_media_source, make_album


def _albums_dir(gallery: Path) -> Path:
    """Return the albums/ subdirectory, creating it if needed."""
    d = gallery / "albums"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestBuildAlbumIdToPathIndex:
    def test_empty_gallery(self, tmp_path: Path) -> None:
        index = build_album_id_to_path_index(tmp_path)
        assert index.id_to_path == {}
        assert index.duplicates == {}

    def test_single_album(self, tmp_path: Path) -> None:
        album_dir, aid = make_album(_albums_dir(tmp_path), "2024-06-15 - Trip")
        index = build_album_id_to_path_index(tmp_path)
        assert index.id_to_path == {aid: album_dir}
        assert index.duplicates == {}

    def test_multiple_albums(self, tmp_path: Path) -> None:
        albums = _albums_dir(tmp_path)
        _, aid1 = make_album(albums, "2024-06-15 - Trip")
        _, aid2 = make_album(albums, "2024-07-20 - Vacation")
        index = build_album_id_to_path_index(tmp_path)
        assert len(index.id_to_path) == 2
        assert aid1 in index.id_to_path
        assert aid2 in index.id_to_path
        assert index.duplicates == {}

    def test_album_without_metadata_raises(self, tmp_path: Path) -> None:
        albums = _albums_dir(tmp_path)
        make_album(albums, "2024-06-15 - Good Album")

        # An empty album.yaml is corrupt, not absent: it must raise rather
        # than be reported (and later "fixed") as a missing ID.
        broken = albums / "2024-07-01 - Broken"
        add_ios_media_source(broken)
        photree_dir = broken / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        with pytest.raises(InvalidMetadataError) as exc_info:
            build_album_id_to_path_index(tmp_path)
        assert exc_info.value.path == photree_dir / "album.yaml"

    def test_duplicate_ids_detected(self, tmp_path: Path) -> None:
        albums = _albums_dir(tmp_path)
        shared_id = generate_album_id()
        dir1, _ = make_album(albums, "2024-06-15 - A", album_id=shared_id)
        dir2, _ = make_album(albums, "2024-06-16 - B", album_id=shared_id)
        index = build_album_id_to_path_index(tmp_path)
        assert shared_id in index.duplicates
        assert set(index.duplicates[shared_id]) == {dir1, dir2}
        # id_to_path still has one entry (first occurrence)
        assert shared_id in index.id_to_path

    def test_nested_album_directories(self, tmp_path: Path) -> None:
        year_dir = tmp_path / "albums" / "2024"
        year_dir.mkdir(parents=True)
        _, aid = make_album(year_dir, "2024-06-15 - Nested")
        index = build_album_id_to_path_index(tmp_path)
        assert aid in index.id_to_path


class TestBuildAlbumIndex:
    def test_empty_list(self) -> None:
        index = build_album_index([])
        assert index.id_to_path == {}
        assert index.duplicates == {}

    def test_builds_index_from_list(self, tmp_path: Path) -> None:
        dir1, aid1 = make_album(tmp_path, "2024-06-15 - Trip")
        dir2, aid2 = make_album(tmp_path, "2024-07-20 - Vacation")
        index = build_album_index([dir1, dir2])
        assert index.id_to_path == {aid1: dir1, aid2: dir2}
        assert index.duplicates == {}

    def test_missing_metadata_raises(self, tmp_path: Path) -> None:
        good_dir, _ = make_album(tmp_path, "2024-06-15 - Good")
        broken = tmp_path / "2024-07-01 - Broken"
        add_ios_media_source(broken)
        photree_dir = broken / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        with pytest.raises(InvalidMetadataError) as exc_info:
            build_album_index([good_dir, broken])
        assert exc_info.value.path == photree_dir / "album.yaml"


class TestResolveAlbumPathById:
    def test_resolves_by_internal_id_from_external(self, tmp_path: Path) -> None:
        """External ID → parse to internal → resolve."""
        dir1, aid1 = make_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_index([dir1])
        external_id = format_album_external_id(aid1)
        internal_id = parse_external_id(external_id, ALBUM_ID_PREFIX)
        assert resolve_album_path_by_id(index.id_to_path, internal_id) == dir1

    def test_resolves_by_internal_id(self, tmp_path: Path) -> None:
        dir1, aid1 = make_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_index([dir1])
        assert resolve_album_path_by_id(index.id_to_path, aid1) == dir1

    def test_raises_for_unknown_id(self, tmp_path: Path) -> None:
        dir1, _ = make_album(tmp_path, "2024-06-15 - Trip")
        index = build_album_index([dir1])
        unknown = format_album_external_id(generate_album_id())
        with pytest.raises(AlbumIdNotFoundError) as info:
            resolve_album_path_by_id(index.id_to_path, unknown)
        assert info.value.album_id == unknown


class TestPlanRenamesFromCsv:
    def _make_index(self, tmp_path: Path) -> dict[str, Path]:
        dir1, aid1 = make_album(tmp_path, "2024-06-15 - Trip to Paris")
        dir2, aid2 = make_album(tmp_path, "2024-07-20 - Beach Vacation")
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
            },
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
            },
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
        index = self._make_index(tmp_path)
        aid = next(iter(index))
        ext_id = format_album_external_id(aid)
        # Get the current title and convert to NFC (should be identity)
        current_name = index[aid].name

        parsed = parse_album_name(current_name)
        assert parsed is not None
        nfc_title = unicodedata.normalize("NFC", parsed.title)
        rows = [
            {
                "id": ext_id,
                "series": "",
                "title": nfc_title,
                "location": "",
            },
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

    def test_every_row_of_a_repeated_id_is_an_error(self, tmp_path: Path) -> None:
        # Regression: two rows for one album planned two renames of it, and
        # the second failed mid-run with "No such file".
        index = self._make_index(tmp_path)
        ext_id = format_album_external_id(next(iter(index)))
        rows = [
            {"id": ext_id, "series": "", "title": "First", "location": ""},
            {"id": ext_id, "series": "", "title": "Second", "location": ""},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert [(e.kind, e.row) for e in errors] == [
            (RenamePlanErrorKind.DUPLICATE_ID, 1),
            (RenamePlanErrorKind.DUPLICATE_ID, 2),
        ]

    @pytest.mark.parametrize(
        ("series", "title", "location"),
        [
            ("", "Paris @ Night", ""),
            ("", "A - B", ""),
            ("A - B", "Trip", ""),
            ("", "Trip", "Paris - Louvre"),
            ("", "Trip [private]", ""),
        ],
    )
    def test_name_that_parses_back_differently_is_an_error(
        self,
        tmp_path: Path,
        series: str,
        title: str,
        location: str,
    ) -> None:
        index = self._make_index(tmp_path)
        ext_id = format_album_external_id(next(iter(index)))
        rows = [
            {"id": ext_id, "series": series, "title": title, "location": location},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert [(e.kind, e.row) for e in errors] == [
            (RenamePlanErrorKind.AMBIGUOUS_NAME, 1),
        ]

    def test_path_separator_in_a_field_is_an_error(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        ext_id = format_album_external_id(next(iter(index)))
        rows = [{"id": ext_id, "series": "", "title": "AC/DC", "location": ""}]
        actions, errors = plan_renames_from_csv(rows, index)
        assert actions == ()
        assert [(e.kind, e.new_name) for e in errors] == [
            (RenamePlanErrorKind.PATH_SEPARATOR, "2024-06-15 - AC/DC"),
        ]

    def test_location_and_series_fields_build_a_name_that_round_trips(
        self,
        tmp_path: Path,
    ) -> None:
        index = self._make_index(tmp_path)
        ext_id = format_album_external_id(next(iter(index)))
        rows = [
            {"id": ext_id, "series": "Europe", "title": "Night", "location": "Paris"},
        ]
        actions, errors = plan_renames_from_csv(rows, index)
        assert errors == ()
        assert [a.new_name for a in actions] == [
            "2024-06-15 - Europe - Night @ Paris",
        ]


class TestGalleryStatsWithoutCache:
    """
    ``gallery stats`` must work before anything has populated a cache.

    Regression: the cache-merge filter tested ``s.file_count > 0`` on a value
    that is ``None`` until some album has a ``.photree/cache/`` directory, so
    the command crashed with an AttributeError on a freshly imported gallery —
    exactly when a user is most likely to run it.
    """

    def test_no_album_cache_does_not_crash(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        (gallery / ".photree").mkdir(parents=True)

        albums = replace(ALBUMS_STATS, cache_storage=None)

        result = compute_gallery_stats(albums, gallery)

        assert result.albums == albums
        assert result.cache_storage is None
