from pathlib import Path

from photree.album.id import format_album_external_id
from tests.fakes import invoke_cli
from tests.testkit import make_gallery, make_gallery_album


def _rename_csv(tmp_path: Path, album_id: str, title: str) -> Path:
    csv_file = tmp_path / "rename.csv"
    csv_file.write_text(
        f"id,series,title,location\n{format_album_external_id(album_id)},,{title},\n",
        encoding="utf-8",
    )
    return csv_file


def _album_names(gallery: Path) -> list[str]:
    return sorted(p.name for p in (gallery / "albums" / "2024").iterdir())


class TestGalleryRenameFromCsv:
    def test_album_is_renamed_by_its_id(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid = make_gallery_album(gallery, "2024-06-15 - Old Title")
        csv_file = _rename_csv(tmp_path, aid, "New Title")

        result = invoke_cli(
            ["gallery", "rename-from-csv", str(csv_file), "-g", str(gallery)],
        )

        assert result.exit_code == 0, result.output
        assert "Renamed 1 album(s)." in result.output
        assert _album_names(gallery) == ["2024-06-15 - New Title"]

    def test_dry_run_renames_nothing(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid = make_gallery_album(gallery, "2024-06-15 - Old Title")
        csv_file = _rename_csv(tmp_path, aid, "New Title")

        result = invoke_cli(
            [
                "gallery",
                "rename-from-csv",
                str(csv_file),
                "-g",
                str(gallery),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "[dry-run] 1 album(s) would be renamed." in result.output
        assert _album_names(gallery) == ["2024-06-15 - Old Title"]

    def test_duplicate_album_id_renames_nothing(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _, aid = make_gallery_album(gallery, "2024-06-15 - Trip")
        make_gallery_album(gallery, "2024-06-16 - Trip copy", album_id=aid)
        csv_file = _rename_csv(tmp_path, aid, "New Title")

        result = invoke_cli(
            ["gallery", "rename-from-csv", str(csv_file), "-g", str(gallery)],
        )

        assert result.exit_code == 1, result.output
        assert "Duplicate album IDs found:" in result.output
        assert "albums fix --new-id" in result.output
        assert _album_names(gallery) == ["2024-06-15 - Trip", "2024-06-16 - Trip copy"]
