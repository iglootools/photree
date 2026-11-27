import csv
import io
from collections.abc import Callable
from pathlib import Path

import pytest

from photree.album.id import format_album_external_id
from photree.album.store.media_sources_discovery import MediaSourceConflictError
from photree.cli import main
from photree.foundation.metadata_io import InvalidMetadataError
from tests.fakes import invoke_cli
from tests.testkit import add_ios_media_source, make_album


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


class TestVersionCommand:
    def test_version_flag(self) -> None:
        result = invoke_cli(["--version"])
        assert result.exit_code == 0
        assert result.output.strip()

    def test_short_version_flag(self) -> None:
        result = invoke_cli(["-V"])
        assert result.exit_code == 0

    def test_no_args_shows_help(self) -> None:
        result = invoke_cli([])
        assert "photree" in result.output.lower()


class TestAlbumsRenameFromCsv:
    def test_rename_title(self, tmp_path: Path) -> None:
        _, aid = make_album(tmp_path, "2024-06-15 - Old Title")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "New Title",
                    "location": "",
                },
            ],
        )
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Renamed 1 album(s)" in result.output
        assert (tmp_path / "2024-06-15 - New Title").is_dir()
        assert not (tmp_path / "2024-06-15 - Old Title").exists()

    def test_dry_run(self, tmp_path: Path) -> None:
        _, aid = make_album(tmp_path, "2024-06-15 - Trip")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "New Trip",
                    "location": "",
                },
            ],
        )
        result = invoke_cli(
            [
                "albums",
                "rename-from-csv",
                str(csv_file),
                "-d",
                str(tmp_path),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "[dry-run] 1 album(s) would be renamed." in result.output
        assert (tmp_path / "2024-06-15 - Trip").is_dir()

    def test_no_changes(self, tmp_path: Path) -> None:
        _, aid = make_album(tmp_path, "2024-06-15 - Trip")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "Trip",
                    "location": "",
                },
            ],
        )
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Nothing to rename" in result.output

    def test_empty_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("id,series,title,location\n")
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_album_dir_option(self, tmp_path: Path) -> None:
        album_dir, aid = make_album(tmp_path, "2024-06-15 - Old")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [
                {
                    "id": format_album_external_id(aid),
                    "series": "",
                    "title": "New",
                    "location": "",
                },
            ],
        )
        result = invoke_cli(
            [
                "albums",
                "rename-from-csv",
                str(csv_file),
                "-a",
                str(album_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Renamed 1 album(s)" in result.output

    def test_csv_with_byte_order_mark_is_read(self, tmp_path: Path) -> None:
        # Regression: the BOM a spreadsheet writes turned the id column into
        # "\ufeffid", so every row failed with "empty album ID".
        _, aid = make_album(tmp_path, "2024-06-15 - Old")
        csv_file = tmp_path / "rename.csv"
        csv_file.write_text(
            f"id,series,title,location\n{format_album_external_id(aid)},,New,\n",
            encoding="utf-8-sig",
        )
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "2024-06-15 - New").is_dir()

    def test_missing_column_renames_nothing(self, tmp_path: Path) -> None:
        # Regression: a CSV without its location column stripped the location
        # from every album.
        _, aid = make_album(tmp_path, "2024-06-15 - Trip @ Paris")
        csv_file = tmp_path / "rename.csv"
        _write_csv(
            csv_file,
            [{"id": format_album_external_id(aid), "series": "", "title": "Trip"}],
        )
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "has no location column(s)" in result.output
        assert (tmp_path / "2024-06-15 - Trip @ Paris").is_dir()

    def test_csv_that_is_not_utf8_is_reported(self, tmp_path: Path) -> None:
        _, aid = make_album(tmp_path, "2024-06-15 - Old")
        csv_file = tmp_path / "rename.csv"
        csv_file.write_text(
            f"id,series,title,location\n{format_album_external_id(aid)},,Été,\n",
            encoding="latin-1",
        )
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 1, result.output
        assert isinstance(result.exception, SystemExit)
        assert "rename.csv is not UTF-8 text" in result.output
        assert (tmp_path / "2024-06-15 - Old").is_dir()

    def test_malformed_csv_is_reported_with_its_line(self, tmp_path: Path) -> None:
        _, aid = make_album(tmp_path, "2024-06-15 - Old")
        csv_file = tmp_path / "rename.csv"
        oversized = "x" * (csv.field_size_limit() + 1)
        csv_file.write_text(
            f"id,series,title,location\n{format_album_external_id(aid)},,{oversized},\n",
            encoding="utf-8",
        )
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 1, result.output
        assert isinstance(result.exception, SystemExit)
        assert "rename.csv, line 2: malformed CSV (field larger" in result.output
        assert (tmp_path / "2024-06-15 - Old").is_dir()

    def test_duplicate_ids_suggest_new_ids_for_the_copy_only(
        self,
        tmp_path: Path,
    ) -> None:
        _, aid = make_album(tmp_path, "2024-06-15 - Trip")
        make_album(tmp_path, "2024-06-15 - Trip copy", album_id=aid)
        csv_file = tmp_path / "rename.csv"
        csv_file.write_text("id,series,title,location\n")
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        output = " ".join(result.output.split())
        assert (
            "'photree albums fix --new-id --album-dir "
            f'"{tmp_path / "2024-06-15 - Trip copy"}"\''
        ) in output

    def test_corrupt_album_yaml_exits(self, tmp_path: Path) -> None:
        # An empty album.yaml is corrupt metadata, not a missing ID: it must
        # stop the run rather than be treated as absent.
        album_dir = tmp_path / "2024-06-15 - Broken"
        add_ios_media_source(album_dir)
        photree_dir = album_dir / ".photree"
        photree_dir.mkdir(parents=True, exist_ok=True)
        (photree_dir / "album.yaml").write_text("")

        csv_file = tmp_path / "rename.csv"
        csv_file.write_text("id,series,title,location\nalbum_x,,,New\n")
        result = invoke_cli(
            ["albums", "rename-from-csv", str(csv_file), "-a", str(album_dir)],
        )
        assert result.exit_code == 1
        assert isinstance(result.exception, InvalidMetadataError)
        assert result.exception.path == album_dir / ".photree" / "album.yaml"


class TestMain:
    def test_reports_media_source_conflict(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A conflict no command wrapped ends in a message and exit 1."""
        album = tmp_path / "2024-07-14 - Trip [private]"

        def _raise(**_: object) -> None:
            raise MediaSourceConflictError(album, ("main",))

        chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(run=_raise)

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "ios-<name>/ and std-<name>/" in err
        # Relative, and "[private]" is not swallowed as Rich markup.
        assert "2024-07-14 - Trip [private] has both" in err
