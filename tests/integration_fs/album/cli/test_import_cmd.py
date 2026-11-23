"""CLI tests for ``photree album import``: what it prints, and its exit code."""

from pathlib import Path

from photree.album.importer.album_import import AlbumImportResult
from photree.album.importer.image_capture import ImportPlan, IosSourceImportResult
from photree.common.sysdeps import SystemDependency
from tests.fakes import fake_album_runtime, invoke_cli
from tests.testkit import write_file


def _std_staged_album(tmp_path: Path, *files: str) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    for f in files:
        write_file(album / "to-import-std-nelu/orig" / f)
    return album


def _import(album: Path, source: Path, *flags: str, result: AlbumImportResult) -> str:
    """Run ``album import`` with *result* as the import's outcome; return output."""

    def _run_import(**_: object) -> AlbumImportResult:
        return result

    invoked = invoke_cli(
        ["album", "import", "-a", str(album), "-s", str(source), *flags],
        runtime=fake_album_runtime(*SystemDependency, run_import=_run_import),
    )
    return f"{invoked.exit_code}\n{invoked.output}"


def _unreachable(**_: object) -> AlbumImportResult:
    msg = "the import must be refused before it runs"
    raise AssertionError(msg)


class TestAlbumImport:
    def test_clean_import_exits_zero(self, tmp_path: Path) -> None:
        album = _std_staged_album(tmp_path, "DSC_0001.JPG")
        (tmp_path / "ic").mkdir()

        output = _import(album, tmp_path / "ic", "--force", result=AlbumImportResult())

        assert output.startswith("0\n")
        assert "Import:" in output

    def test_unprocessed_selection_entries_exit_one(self, tmp_path: Path) -> None:
        album = _std_staged_album(tmp_path, "DSC_0001.JPG")
        (tmp_path / "ic").mkdir()
        result = AlbumImportResult(
            ios_results=(
                IosSourceImportResult(
                    media_source_name="main",
                    plan=ImportPlan(matches=(), unmatched=()),
                    processed=frozenset(),
                    unprocessed=("IMG_0001.HEIC",),
                ),
            ),
        )

        output = _import(album, tmp_path / "ic", "--force", result=result)

        assert output.startswith("1\n")
        assert "Remove them before the next import" in output
        assert "- IMG_0001.HEIC" in output

    def test_validation_error_names_its_source_and_stops(self, tmp_path: Path) -> None:
        album = _std_staged_album(tmp_path, "DSC_0001.JPG", "DSC_0001.CR2")
        (tmp_path / "ic").mkdir()

        invoked = invoke_cli(
            ["album", "import", "-a", str(album), "-s", str(tmp_path / "ic")],
            runtime=fake_album_runtime(*SystemDependency, run_import=_unreachable),
        )

        assert invoked.exit_code == 1
        assert "Validation failed for 2024-07-14 - Trip:" in invoked.output
        assert "- [std:nelu] 1 entry(ies) would not be imported: orig/DSC_0001.CR2" in (
            invoked.output
        )
        assert (album / "to-import-std-nelu/orig/DSC_0001.CR2").is_file()

    def test_failed_image_capture_check_points_to_force(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Trip"
        write_file(album / "to-import-ios-main/IMG_0001.HEIC")
        write_file(tmp_path / "ic/notes.txt")
        (tmp_path / "ic/backup").mkdir()

        invoked = invoke_cli(
            ["album", "import", "-a", str(album), "-s", str(tmp_path / "ic")],
            runtime=fake_album_runtime(*SystemDependency, run_import=_unreachable),
        )

        assert invoked.exit_code == 1
        assert "does not look like an Image Capture folder" in invoked.output
        assert "- Found 1 subdirectory(ies): backup." in invoked.output
        assert "--force to the import command" in invoked.output
        assert "Nothing was imported." in invoked.output
