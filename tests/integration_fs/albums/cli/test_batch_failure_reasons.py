"""
Every batch command must say *why* an item failed, not just that it did.

A batch that reports only which albums failed forces a per-album re-run to
learn anything the batch already knew. These pin the reason to the output.
"""

from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import ALBUM_YAML, AlbumMetadata
from photree.albums.batchcli.failures import batch_failures_report, investigate_commands
from photree.albums.cmd_handler import BatchFailure
from photree.albums.cmd_handler.fix import batch_fix
from photree.albums.cmd_handler.init import batch_init
from photree.foundation.layout import PHOTREE_DIR
from tests.fakes import invoke_cli
from tests.testkit import write_file


def _album(base: Path, name: str) -> Path:
    album = base / name
    write_file(album / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    return album


class TestBatchInit:
    def test_reason_is_printed_for_an_already_initialized_album(
        self,
        tmp_path: Path,
    ) -> None:
        _album(tmp_path, "2024-07-14 - Hiking")

        result = invoke_cli(["albums", "init", "-d", str(tmp_path)])

        assert result.exit_code == 1
        assert "Failed albums:" in result.output
        assert "already initialized" in result.output
        assert "To investigate failures:" in result.output

    def test_retry_command_stays_a_dry_run(self, tmp_path: Path) -> None:
        _album(tmp_path, "2024-07-14 - Hiking")

        result = invoke_cli(["albums", "init", "-d", str(tmp_path), "--dry-run"])

        assert result.exit_code == 1
        assert 'album init --album-dir "' in result.output
        assert '2024-07-14 - Hiking" --dry-run' in result.output

    def test_one_command_retries_every_failed_album(self, tmp_path: Path) -> None:
        _album(tmp_path, "2024-07-14 - Hiking")
        _album(tmp_path, "2024-07-15 - Beach")

        result = invoke_cli(["albums", "init", "-d", str(tmp_path), "--dry-run"])

        assert result.exit_code == 1
        retry_all = result.output.split("To retry them all:")[1].strip()
        assert retry_all == (
            f'photree albums init -a "{tmp_path / "2024-07-14 - Hiking"}" '
            f'-a "{tmp_path / "2024-07-15 - Beach"}" --dry-run'
        )


class TestBatchRefresh:
    def test_jpeg_failure_reason_reaches_the_summary(self, tmp_path: Path) -> None:
        # A .HEIC whose bytes are not HEIC: sips rejects it on macOS, and the
        # is missing (FileNotFoundError) everywhere else.
        album = tmp_path / "2024-07-14 - Hiking"
        write_file(album / "ios-main" / "orig-img" / "IMG_0001.HEIC", "not heic")
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))

        result = invoke_cli(["albums", "refresh", "-d", str(tmp_path)])

        assert result.exit_code == 1
        assert "Failed albums:" in result.output
        assert "IMG_0001" in result.output
        assert "0 album(s) refreshed, 1 failed" in result.output

    def test_retry_command_repeats_the_run_flags(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        write_file(album / "ios-main" / "orig-img" / "IMG_0001.HEIC", "not heic")
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))

        result = invoke_cli(
            ["albums", "refresh", "-d", str(tmp_path), "--refresh-jpeg"],
        )

        assert result.exit_code == 1
        assert '2024-07-14 - Hiking" --refresh-jpeg' in result.output


class TestBatchFailureReport:
    """The shared formatter pairs each album with its reason."""

    def test_formats_path_and_reason(self, tmp_path: Path) -> None:
        report = batch_failures_report(
            [BatchFailure(album_dir=tmp_path / "a", reason="disk on fire")],
            tmp_path,
        )

        assert "a" in report
        assert "disk on fire" in report


class TestInvestigateCommands:
    def test_a_single_failure_gets_no_retry_all_command(self, tmp_path: Path) -> None:
        commands = investigate_commands("refresh", [tmp_path / "a"], tmp_path)

        assert commands.splitlines() == [
            "",
            "To investigate failures:",
            '  photree album refresh --album-dir "a"',
        ]

    def test_several_failures_get_one_retry_all_command(self, tmp_path: Path) -> None:
        commands = investigate_commands(
            "refresh",
            [tmp_path / "a", tmp_path / "b"],
            tmp_path,
            extra_flags=" --refresh-jpeg",
        )

        assert commands.splitlines()[-2:] == [
            "To retry them all:",
            '  photree albums refresh -a "a" -a "b" --refresh-jpeg',
        ]


class TestHandlerFailureReasons:
    """
    Each handler keeps the reason of a failed album, not only its path.

    Refresh and fix-ios are covered in test_face_failure_propagation.py and
    albums/test_batch_fix_ios.py.
    """

    def test_init_failure_reason_names_the_existing_id(self, tmp_path: Path) -> None:
        album = _album(tmp_path, "2024-07-14 - Hiking")

        result = batch_init([album])

        assert [f.album_dir for f in result.failures] == [album]
        assert result.failures[0].reason.startswith("already initialized: ")

    def test_fix_failure_reason_names_the_unreadable_metadata(
        self,
        tmp_path: Path,
    ) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        write_file(album / PHOTREE_DIR / ALBUM_YAML, "id: [not, an, id")

        result = batch_fix([album], fix_id=True)

        assert [f.album_dir for f in result.failures] == [album]
        assert ALBUM_YAML in result.failures[0].reason
