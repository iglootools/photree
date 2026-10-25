"""Tests for the light check run before ``album import``."""

from pathlib import Path

from photree.album.importer.naming_gate import check_import_naming
from photree.album.store.protocol import ALBUM_YAML
from photree.foundation.layout import PHOTREE_DIR


def _existing_album(parent: Path, name: str) -> Path:
    """An album discovered by ``discover_albums``: metadata plus an archive."""
    album = parent / name
    (album / PHOTREE_DIR).mkdir(parents=True)
    (album / PHOTREE_DIR / ALBUM_YAML).write_text(
        "id: 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1\n"
    )
    (album / "ios-main" / "orig-img").mkdir(parents=True)
    return album


def _staged_album(parent: Path, name: str) -> Path:
    album = parent / name
    album.mkdir(parents=True)
    return album


class TestCheckImportNaming:
    def test_valid_album_passes(self, tmp_path: Path) -> None:
        album = _staged_album(tmp_path, "2024-07-01 - Hike")
        assert check_import_naming([album]).success

    def test_reports_naming_issues(self, tmp_path: Path) -> None:
        album = _staged_album(tmp_path, "2024-07-01 - 01- Hike")
        check = check_import_naming([album])
        assert [a for a, _ in check.naming_errors] == [album]

    def test_collision_with_sibling_album(self, tmp_path: Path) -> None:
        _existing_album(tmp_path, "2024-07-01 - Dinner")
        album = _staged_album(tmp_path, "2024-07-01 - Hike")
        check = check_import_naming([album])
        assert [d for d, _ in check.date_collisions] == ["2024-07-01"]

    def test_part_numbers_disambiguate(self, tmp_path: Path) -> None:
        _existing_album(tmp_path, "2024-07-01 - 01 - Dinner")
        album = _staged_album(tmp_path, "2024-07-01 - 02 - Hike")
        assert check_import_naming([album]).success

    def test_ignores_collisions_between_other_siblings(self, tmp_path: Path) -> None:
        _existing_album(tmp_path, "2024-07-01 - Dinner")
        _existing_album(tmp_path, "2024-07-01 - Lunch")
        album = _staged_album(tmp_path, "2024-07-02 - Hike")
        assert check_import_naming([album]).success
