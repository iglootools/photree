"""CLI regressions for album commands: corrupt metadata, structured errors,
and copy-pasteable suggestions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.album.importer import album_import
from photree.album.importer.album_import import (
    AlbumImportResult,
    EmptyImageCaptureDirError,
)
from photree.album.importer.collision import ImportCollisionError
from photree.album.store.media_sources_discovery import MediaSourceConflictError
from photree.album.store.protocol import std_media_source
from photree.cli import app
from photree.fsprotocol import SHARE_SENTINEL, InvalidMetadataError

runner = CliRunner()

_TRUNCATED_YAML = "id: [0192d4e1"


def _empty_config(tmp_path: Path) -> Path:
    """An empty config file, so the test never reads the user's own config."""
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
    tmp_path: Path, args: list[str]
) -> None:
    """A truncated album.yaml must stop the command, not get a fresh ID."""
    album = _corrupt_album(tmp_path)

    result = runner.invoke(app, [*args, "--album-dir", str(album)])

    assert result.exit_code != 0
    assert isinstance(result.exception, InvalidMetadataError)
    assert (album / ".photree/album.yaml").read_text(
        encoding="utf-8"
    ) == _TRUNCATED_YAML


def test_fix_without_flag_suggests_help(tmp_path: Path) -> None:
    result = runner.invoke(app, ["album", "fix", "--album-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "No fix specified." in result.output
    assert "'photree album fix --help'" in result.output


def test_rm_upstream_refusal_suggests_force(tmp_path: Path) -> None:
    _write(tmp_path / "std-nelu/orig-vid/clip.mov")
    (tmp_path / "nelu-vid").mkdir()

    result = runner.invoke(
        app, ["album", "fix", "--rm-upstream", "--album-dir", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "--force" in result.output
    assert (tmp_path / "std-nelu/orig-vid/clip.mov").exists()


def test_rm_media_error_uses_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album = tmp_path / "album"
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["album", "rm-media", "--album-dir", str(album), "unknown/IMG_0001.jpg"]
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

    result = runner.invoke(app, ["album", "check", "--album-dir", str(album)])

    assert result.exit_code == 1
    assert "ios-<name>/ and std-<name>/" in result.output
    assert "main" in result.output


def test_list_media_csv_keeps_stdout_clean(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["album", "list-media", "--album-dir", str(tmp_path), "--format", "csv"]
    )

    assert result.exit_code == 0
    assert "No media metadata found" in result.stderr
    assert result.stdout == ""
    assert "--album-dir" in result.stderr


def test_list_media_rejects_unknown_format(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["album", "list-media", "--album-dir", str(tmp_path), "--format", "json"]
    )

    assert result.exit_code == 2


def test_show_uses_indented_details(tmp_path: Path) -> None:
    album = tmp_path / "2024-07-14 - 01 - Trip @ Banff"
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")

    result = runner.invoke(app, ["album", "show", "--album-dir", str(album)])

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

    result = runner.invoke(
        app,
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


def _stub_system_deps(bin_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Put no-op sips/exiftool stubs on PATH so the preflight gate passes."""
    bin_dir.mkdir()
    for name in ("sips", "exiftool"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def _std_staged_album(tmp_path: Path) -> Path:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "to-import-std-nelu/orig/DSC_0001.JPG")
    return album


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            lambda album: EmptyImageCaptureDirError(album.parent / "ic"),
            "Could not find any image capture files",
        ),
        (
            lambda album: ImportCollisionError(std_media_source("nelu"), ("DSC_0001",)),
            "Rename to-import-std-nelu",
        ),
    ],
)
def test_import_refusal_is_reported_not_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Callable[[Path], Exception],
    expected: str,
) -> None:
    """run_import's own refusals end in a message and exit 1, not a traceback."""
    _stub_system_deps(tmp_path / "bin", monkeypatch)
    album = _std_staged_album(tmp_path)
    (tmp_path / "ic").mkdir()

    def _refuse(**_: object) -> AlbumImportResult:
        raise error(album)

    monkeypatch.setattr(album_import, "run_import", _refuse)

    result = runner.invoke(
        app,
        ["album", "import", "-a", str(album), "-s", str(tmp_path / "ic"), "--force"],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert expected in result.output


def test_entry_point_reports_media_source_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A conflict no command wrapped ends in a message and exit 1."""
    import photree.cli as cli_module

    album = tmp_path / "2024-07-14 - Trip [private]"

    def _raise() -> None:
        raise MediaSourceConflictError(album, ("main",))

    monkeypatch.setattr(cli_module, "app", _raise)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        cli_module.main()

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

    refused = runner.invoke(app, args)

    assert refused.exit_code == 1
    assert (album / "std-nelu/orig-vid/clip.mov").exists()
    assert "--rm-upstream --force" not in refused.output
    assert "--rm-upstream" in refused.output  # retry command keeps the fix flag

    forced = runner.invoke(app, [*args, "--force"])

    assert forced.exit_code == 0, forced.output
    assert not (album / "std-nelu/orig-vid/clip.mov").exists()


def test_gallery_fix_invalid_flags_suggest_help(tmp_path: Path) -> None:
    result = runner.invoke(app, ["gallery", "fix", "--gallery-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "'photree gallery fix --help'" in result.output


def test_export_missing_sentinel_suggests_quoted_relative_touch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "main-jpg/IMG_0001.jpg")
    (tmp_path / "my share").mkdir()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
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
    from photree.album.exporter.settings import (
        ExportSettingsError,
        ExportSettingsErrorKind,
        ResolvedExportSettings,
        validate_export_settings,
    )
    from photree.fsprotocol import AlbumShareLayout, LinkMode, ShareDirectoryLayout

    with pytest.raises(ExportSettingsError) as exc_info:
        validate_export_settings(
            ResolvedExportSettings(
                share_dir=tmp_path,
                share_layout=ShareDirectoryLayout.FLAT,
                album_layout=AlbumShareLayout.BROWSABLE_JPG,
                link_mode=LinkMode.HARDLINK,
            )
        )

    assert exc_info.value.kind == ExportSettingsErrorKind.MISSING_SENTINEL
    assert exc_info.value.share_dir == tmp_path
