"""
CLI regressions for album commands.

Corrupt metadata, structured errors, and copy-pasteable suggestions.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from photree.album.exporter.settings import (
    ExportSettingsError,
    ExportSettingsErrorKind,
    ResolvedExportSettings,
    validate_export_settings,
)
from photree.album.id import generate_album_id
from photree.album.importer.album_import import (
    AlbumImportResult,
    EmptyImageCaptureDirError,
)
from photree.album.importer.collision import ImportCollisionError
from photree.album.store.media_source import std_media_source
from photree.album.store.media_sources_discovery import MediaSourceConflictError
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import main
from photree.common.sysdeps import SystemDependency
from photree.foundation.layout import SHARE_SENTINEL
from photree.foundation.linking import LinkMode
from photree.foundation.metadata_io import InvalidMetadataError
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout
from tests.fakes import fake_album_runtime, invoke_cli

_TRUNCATED_YAML = "id: [0192d4e1"


def _empty_config(tmp_path: Path) -> Path:
    """Write an empty config file, so the test never reads the user's own config."""
    config = tmp_path / "empty.toml"
    config.write_text("", encoding="utf-8")
    return config


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _corrupt_album(tmp_path: Path) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")
    _write(album / ".photree/album.yaml", _TRUNCATED_YAML)
    return album


@pytest.mark.parametrize(
    "args",
    [
        ["album", "init"],
        ["album", "fix", "--id"],
        ["album", "fix", "--new-id"],
    ],
)
def test_corrupt_album_yaml_is_never_overwritten(
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


def test_fix_without_flag_suggests_help(tmp_path: Path) -> None:
    result = invoke_cli(["album", "fix", "--album-dir", str(tmp_path)])

    assert result.exit_code == 2
    assert "No fix specified." in result.output
    assert "'photree album fix --help'" in result.output


def test_fix_ios_mutually_exclusive_flags_exit_2(tmp_path: Path) -> None:
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


def test_rm_media_without_files_exits_2(tmp_path: Path) -> None:
    result = invoke_cli(["album", "rm-media", "--album-dir", str(tmp_path)])

    assert result.exit_code == 2
    assert "No files specified." in result.output


def test_rm_upstream_refusal_suggests_force(tmp_path: Path) -> None:
    _write(tmp_path / "std-nelu/orig-vid/clip.mov")
    (tmp_path / "nelu-vid").mkdir()

    result = invoke_cli(["album", "fix", "--rm-upstream", "--album-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "--force" in result.output
    assert (tmp_path / "std-nelu/orig-vid/clip.mov").exists()


def test_rm_media_error_uses_relative_path(
    tmp_path: Path,
    chdir: Callable[[Path], None],
) -> None:
    album = tmp_path / "album"
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")
    chdir(tmp_path)

    result = invoke_cli(
        ["album", "rm-media", "--album-dir", str(album), "unknown/IMG_0001.jpg"],
    )

    assert result.exit_code == 1
    assert 'Directory "unknown" does not match any media source in album.' in (
        result.output
    )
    assert str(tmp_path) not in result.output


def test_media_source_conflict_is_reported_by_check(tmp_path: Path) -> None:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")
    _write(album / "std-main/orig-img/DSC_0001.JPG")

    result = invoke_cli(["album", "check", "--album-dir", str(album)])

    assert result.exit_code == 1
    assert "ios-<name>/ and std-<name>/" in result.output
    assert "main" in result.output


def test_list_media_csv_keeps_stdout_clean(tmp_path: Path) -> None:
    result = invoke_cli(
        ["album", "list-media", "--album-dir", str(tmp_path), "--format", "csv"],
    )

    assert result.exit_code == 0
    assert "No media metadata found" in result.stderr
    assert result.stdout == ""
    assert "--album-dir" in result.stderr


def test_list_media_rejects_unknown_format(tmp_path: Path) -> None:
    result = invoke_cli(
        ["album", "list-media", "--album-dir", str(tmp_path), "--format", "json"],
    )

    assert result.exit_code == 2


def test_show_uses_indented_details(tmp_path: Path) -> None:
    album = tmp_path / "2024-07-14 - 01 - Trip @ Banff"
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")

    result = invoke_cli(["album", "show", "--album-dir", str(album)])

    assert result.exit_code == 0
    assert "  part: 01\n" in result.output
    assert "  location: Banff\n" in result.output
    assert "  media sources: main (ios)\n" in result.output


def test_export_unplaceable_name_is_reported(tmp_path: Path) -> None:
    """A name the share layout cannot place is an error, not a traceback."""
    album = tmp_path / "2024 - Family"
    _write(album / "main-jpg/IMG_0001.jpg")
    share = tmp_path / "share"
    _write(share / SHARE_SENTINEL, "")

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


def _std_staged_album(tmp_path: Path) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "to-import-std-nelu/orig/DSC_0001.JPG")
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
]


@pytest.mark.parametrize(("error", "expected"), _IMPORT_REFUSALS)
def test_import_refusal_is_reported_not_raised(
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
        ["album", "import", "-a", str(album), "-s", str(tmp_path / "ic"), "--force"],
        runtime=fake_album_runtime(*SystemDependency, run_import=_refuse),
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert expected in result.output


def test_import_refuses_date_collision_with_sibling(tmp_path: Path) -> None:
    """Album import runs the same light check as gallery import."""
    album = _std_staged_album(tmp_path)
    sibling = tmp_path / "2024-07-14 - Dinner"
    _write(sibling / "std-main/orig-img/DSC_0002.JPG")
    _write(
        sibling / ".photree/album.yaml",
        "id: 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1\n",
    )
    (tmp_path / "ic").mkdir()

    result = invoke_cli(
        ["album", "import", "-a", str(album), "-s", str(tmp_path / "ic"), "--force"],
    )

    assert result.exit_code == 1
    assert "date collision on 2024-07-14" in result.output
    # Refused before importing anything: the staging entry is left as it was.
    assert not (album / "std-nelu").exists()
    assert (album / "to-import-std-nelu/orig/DSC_0001.JPG").is_file()


def test_entry_point_reports_media_source_conflict(
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


def _emptied_std_album(tmp_path: Path) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "std-nelu/orig-vid/clip.mov")
    (album / "nelu-vid").mkdir()
    return album


def test_albums_fix_rm_upstream_refusal_then_force(tmp_path: Path) -> None:
    """Batch rm-upstream refuses an emptied archive unless --force is given."""
    album = _emptied_std_album(tmp_path)
    args = ["albums", "fix", "--rm-upstream", "--album-dir", str(album)]

    refused = invoke_cli(args)

    assert refused.exit_code == 1
    assert (album / "std-nelu/orig-vid/clip.mov").exists()
    assert "--rm-upstream --force" not in refused.output
    assert "--rm-upstream" in refused.output  # retry command keeps the fix flag

    forced = invoke_cli([*args, "--force"])

    assert forced.exit_code == 0, forced.output
    assert not (album / "std-nelu/orig-vid/clip.mov").exists()


def _album_with_id(parent: Path, name: str) -> tuple[Path, str]:
    album = parent / name
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")
    album_id = generate_album_id()
    save_album_metadata(album, AlbumMetadata(id=album_id))
    return album, album_id


def _album_id(album: Path) -> str | None:
    meta = load_album_metadata(album)
    return meta.id if meta is not None else None


def test_albums_fix_new_id_on_a_scan_exits_2(tmp_path: Path) -> None:
    # Regression: a scan gave every album found a new ID, orphaning every
    # collection and face reference to them.
    album, album_id = _album_with_id(tmp_path, "2024-07-14 - Trip")

    result = invoke_cli(["albums", "fix", "--new-id", "--dir", str(tmp_path)])

    assert result.exit_code == 2
    assert "'photree albums fix --new-id --album-dir <album>'" in result.output
    assert _album_id(album) == album_id


def test_albums_fix_new_id_changes_only_the_named_albums(tmp_path: Path) -> None:
    named, named_id = _album_with_id(tmp_path, "2024-07-14 - Trip copy")
    other, other_id = _album_with_id(tmp_path, "2024-07-14 - Trip")

    result = invoke_cli(["albums", "fix", "--new-id", "--album-dir", str(named)])

    assert result.exit_code == 0, result.output
    assert _album_id(named) not in (None, named_id)
    assert _album_id(other) == other_id


def test_gallery_fix_has_no_new_id(tmp_path: Path) -> None:
    result = invoke_cli(["gallery", "fix", "--new-id", "--gallery-dir", str(tmp_path)])

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_gallery_fix_invalid_flags_suggest_help(tmp_path: Path) -> None:
    result = invoke_cli(["gallery", "fix", "--gallery-dir", str(tmp_path)])

    assert result.exit_code == 2
    assert "'photree gallery fix --help'" in result.output


def test_export_missing_sentinel_suggests_quoted_relative_touch(
    tmp_path: Path,
    chdir: Callable[[Path], None],
) -> None:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "main-jpg/IMG_0001.jpg")
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


def test_export_settings_error_is_structured(tmp_path: Path) -> None:
    with pytest.raises(ExportSettingsError) as exc_info:
        validate_export_settings(
            ResolvedExportSettings(
                share_dir=tmp_path,
                share_layout=ShareDirectoryLayout.FLAT,
                album_layout=AlbumShareLayout.BROWSABLE_JPG,
                link_mode=LinkMode.HARDLINK,
            ),
        )

    assert exc_info.value.kind == ExportSettingsErrorKind.MISSING_SENTINEL
    assert exc_info.value.share_dir == tmp_path


def test_album_fix_rm_upstream_refusal_suggestion_keeps_the_run_flags(
    tmp_path: Path,
) -> None:
    album = _emptied_std_album(tmp_path)

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
    assert "--rm-upstream --force --rm-orphan --dry-run --album-dir" in (refused.output)
