"""
CLI regressions for album commands.

Corrupt metadata, structured errors, and copy-pasteable suggestions.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from photree.album.importer.album_import import (
    AlbumImportResult,
    EmptyImageCaptureDirError,
)
from photree.album.importer.collision import (
    ImportCollisionError,
    MediaSourceClash,
    MediaSourceClashError,
    MediaSourceClashErrorKind,
)
from photree.album.store.media_source import std_media_source
from photree.common.sysdeps import SystemDependency
from photree.foundation.layout import SHARE_SENTINEL
from photree.foundation.metadata_io import InvalidMetadataError
from tests.fakes import fake_album_runtime, invoke_cli
from tests.testkit import (
    add_emptied_std_media_source,
    add_incomplete_jpg_dir,
    mark_album,
    write_file,
)

_TRUNCATED_YAML = "id: [0192d4e1"


def _empty_config(tmp_path: Path) -> Path:
    """Write an empty config file, so the test never reads the user's own config."""
    config = tmp_path / "empty.toml"
    config.write_text("", encoding="utf-8")
    return config


def _corrupt_album(tmp_path: Path) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    write_file(album / "ios-main/orig-img/IMG_0001.HEIC")
    write_file(album / ".photree/album.yaml", _TRUNCATED_YAML)
    return album


def _std_staged_album(tmp_path: Path) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    write_file(album / "to-import-std-nelu/orig/DSC_0001.JPG")
    return album


_IMPORT_REFUSALS: list[tuple[Callable[[Path], Exception], str]] = [
    (
        lambda album: EmptyImageCaptureDirError(album.parent / "ic"),
        "Could not find any image capture files",
    ),
    (
        lambda _album: ImportCollisionError(std_media_source("nelu"), ("DSC_0001",)),
        "Rename to-import-std-nelu",
    ),
    (
        lambda _album: MediaSourceClashError(
            MediaSourceClash(
                std_media_source("nelu"),
                MediaSourceClashErrorKind.EXISTING_ARCHIVE,
            ),
        ),
        "the album already has ios-nelu/",
    ),
]


class TestCorruptAlbumMetadata:
    @pytest.mark.parametrize(
        "args",
        [
            ["album", "init"],
            ["album", "fix", "--id"],
            ["album", "fix", "--new-id"],
        ],
    )
    def test_corrupt_album_yaml_is_never_overwritten(
        self,
        tmp_path: Path,
        args: list[str],
    ) -> None:
        """A truncated album.yaml must stop the command, not get a fresh ID."""
        album = _corrupt_album(tmp_path)

        result = invoke_cli([*args, "--album-dir", str(album)])

        assert result.exit_code != 0
        assert isinstance(result.exception, InvalidMetadataError)
        assert (album / ".photree/album.yaml").read_text(
            encoding="utf-8",
        ) == _TRUNCATED_YAML


class TestAlbumFix:
    def test_fix_without_flag_suggests_help(self, tmp_path: Path) -> None:
        result = invoke_cli(["album", "fix", "--album-dir", str(tmp_path)])

        assert result.exit_code == 2
        assert "No fix specified." in result.output
        assert "'photree album fix --help'" in result.output

    def test_rm_upstream_refusal_suggests_force(self, tmp_path: Path) -> None:
        add_emptied_std_media_source(tmp_path)

        result = invoke_cli(
            ["album", "fix", "--rm-upstream", "--album-dir", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "--force" in result.output
        assert (tmp_path / "std-nelu/orig-vid/clip.mov").exists()

    def test_rm_upstream_on_an_incomplete_refresh_suggests_refresh(
        self,
        tmp_path: Path,
    ) -> None:
        album = tmp_path / "album"
        add_incomplete_jpg_dir(album)

        result = invoke_cli(
            ["album", "fix", "--rm-upstream", "--force", "--album-dir", str(album)],
        )

        assert result.exit_code == 1
        assert "main-jpg/" in result.output
        assert "photree album refresh --album-dir" in result.output
        assert (album / "ios-main/orig-img/IMG_0002.HEIC").exists()

    def test_rm_upstream_refusal_suggestion_keeps_the_run_flags(
        self,
        tmp_path: Path,
    ) -> None:
        album = tmp_path / "2024-07-14 - Trip"
        add_emptied_std_media_source(album)

        refused = invoke_cli(
            [
                "album",
                "fix",
                "--rm-upstream",
                "--rm-orphan",
                "--dry-run",
                "--album-dir",
                str(album),
            ],
        )

        assert refused.exit_code == 1
        assert "--rm-upstream --force --rm-orphan --dry-run --album-dir" in (
            refused.output
        )


class TestAlbumFixIos:
    def test_mutually_exclusive_flags_exit_2(self, tmp_path: Path) -> None:
        result = invoke_cli(
            [
                "album",
                "fix-ios",
                "--album-dir",
                str(tmp_path),
                "--rm-miscategorized",
                "--mv-miscategorized",
            ],
        )

        assert result.exit_code == 2
        assert "are mutually exclusive." in result.output
        assert "'photree album fix-ios --help'" in result.output


class TestAlbumRmMedia:
    def test_rm_media_without_files_exits_2(self, tmp_path: Path) -> None:
        result = invoke_cli(["album", "rm-media", "--album-dir", str(tmp_path)])

        assert result.exit_code == 2
        assert "No files specified." in result.output

    def test_rm_media_error_uses_relative_path(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        album = tmp_path / "album"
        write_file(album / "ios-main/orig-img/IMG_0001.HEIC")
        chdir(tmp_path)

        result = invoke_cli(
            ["album", "rm-media", "--album-dir", str(album), "unknown/IMG_0001.jpg"],
        )

        assert result.exit_code == 1
        assert 'Directory "unknown" does not match any media source in album.' in (
            result.output
        )
        assert str(tmp_path) not in result.output


class TestAlbumCheck:
    def test_media_source_conflict_is_reported(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Trip"
        write_file(album / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(album / "std-main/orig-img/DSC_0001.JPG")

        result = invoke_cli(["album", "check", "--album-dir", str(album)])

        assert result.exit_code == 1
        assert "ios-<name>/ and std-<name>/" in result.output
        assert "main" in result.output


class TestAlbumListMedia:
    def test_csv_keeps_stdout_clean(self, tmp_path: Path) -> None:
        result = invoke_cli(
            ["album", "list-media", "--album-dir", str(tmp_path), "--format", "csv"],
        )

        assert result.exit_code == 0
        assert "No media metadata found" in result.stderr
        assert result.stdout == ""
        assert "--album-dir" in result.stderr

    def test_unknown_format_is_rejected(self, tmp_path: Path) -> None:
        result = invoke_cli(
            ["album", "list-media", "--album-dir", str(tmp_path), "--format", "json"],
        )

        assert result.exit_code == 2


class TestAlbumShow:
    def test_details_are_indented(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - 01 - Trip @ Banff"
        write_file(album / "ios-main/orig-img/IMG_0001.HEIC")

        result = invoke_cli(["album", "show", "--album-dir", str(album)])

        assert result.exit_code == 0
        assert "  part: 01\n" in result.output
        assert "  location: Banff\n" in result.output
        assert "  media sources: main (ios)\n" in result.output


class TestAlbumExport:
    def test_unplaceable_name_is_reported(self, tmp_path: Path) -> None:
        """A name the share layout cannot place is an error, not a traceback."""
        album = tmp_path / "2024 - Family"
        write_file(album / "main-jpg/IMG_0001.jpg")
        share = tmp_path / "share"
        write_file(share / SHARE_SENTINEL, "")

        result = invoke_cli(
            [
                "album",
                "export",
                "--album-dir",
                str(album),
                "--share-dir",
                str(share),
                "--share-layout",
                "by-month",
                "--config",
                str(_empty_config(tmp_path)),
            ],
        )

        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "YYYY-MM" in result.output
        assert "--share-layout flat" in result.output

    def test_missing_sentinel_suggests_quoted_relative_touch(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        album = tmp_path / "2024-07-14 - Trip"
        write_file(album / "main-jpg/IMG_0001.jpg")
        (tmp_path / "my share").mkdir()
        chdir(tmp_path)

        result = invoke_cli(
            [
                "album",
                "export",
                "--album-dir",
                str(album),
                "--share-dir",
                str(tmp_path / "my share"),
                "--config",
                str(_empty_config(tmp_path)),
            ],
        )

        assert result.exit_code == 1
        assert "sentinel file: my share\n" in result.output
        assert f"  touch 'my share/{SHARE_SENTINEL}'" in result.output
        assert str(tmp_path) not in result.output


class TestAlbumImport:
    @pytest.mark.parametrize(("error", "expected"), _IMPORT_REFUSALS)
    def test_refusal_is_reported_not_raised(
        self,
        tmp_path: Path,
        error: Callable[[Path], Exception],
        expected: str,
    ) -> None:
        """
        run_import's own refusals end in a message and exit 1, not a traceback.

        The pre-validation refuses both first, so only a change between the two
        (the Image Capture directory emptied, the archive written to) reaches
        run_import's re-check: a fault no real resource produces at that point.
        """
        album = _std_staged_album(tmp_path)
        (tmp_path / "ic").mkdir()

        def _refuse(**_: object) -> AlbumImportResult:
            raise error(album)

        result = invoke_cli(
            [
                "album",
                "import",
                "-a",
                str(album),
                "-s",
                str(tmp_path / "ic"),
                "--force",
            ],
            runtime=fake_album_runtime(*SystemDependency, run_import=_refuse),
        )

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)
        assert expected in result.output

    def test_date_collision_with_sibling_is_refused(self, tmp_path: Path) -> None:
        """Album import runs the same light check as gallery import."""
        album = _std_staged_album(tmp_path)
        sibling = tmp_path / "2024-07-14 - Dinner"
        write_file(sibling / "std-main/orig-img/DSC_0002.JPG")
        mark_album(sibling)
        (tmp_path / "ic").mkdir()

        result = invoke_cli(
            [
                "album",
                "import",
                "-a",
                str(album),
                "-s",
                str(tmp_path / "ic"),
                "--force",
            ],
        )

        assert result.exit_code == 1
        assert "date collision on 2024-07-14" in result.output
        # Refused before importing anything: the staging entry is left as it was.
        assert not (album / "std-nelu").exists()
        assert (album / "to-import-std-nelu/orig/DSC_0001.JPG").is_file()
