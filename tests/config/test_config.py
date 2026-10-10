"""Tests for photree.config module.

The loader takes its environment (``environ``, ``home``, platformdirs
lookups) as parameters, so these tests pass values instead of patching.
"""

from pathlib import Path
from textwrap import dedent

import pytest

from photree.config import (
    ConfigError,
    ConfigErrorKind,
    PhotreeConfig,
    config_search_paths,
    find_config_file,
    load_config,
)
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


def _isolated_find(tmp_path: Path, xdg: Path | None = None) -> Path | None:
    """find_config_file with every search path under *tmp_path*."""
    return find_config_file(
        environ={"XDG_CONFIG_HOME": str(xdg or tmp_path / "empty-xdg")},
        home=tmp_path / "home",
        user_dir=lambda _app: str(tmp_path / "empty-user"),
        site_dir=lambda _app: str(tmp_path / "empty-site"),
    )


def _write_config(tmp_path: Path, content: str) -> str:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(dedent(content), encoding="utf-8")
    return str(cfg_file)


def _load_error(tmp_path: Path, content: str) -> ConfigError:
    with pytest.raises(ConfigError) as exc_info:
        load_config(_write_config(tmp_path, content), home=tmp_path / "home")
    return exc_info.value


class TestConfigSearchPaths:
    def test_returns_deduplicated_paths(self, tmp_path: Path) -> None:
        same = str(tmp_path / "same")
        paths = config_search_paths(
            environ={"XDG_CONFIG_HOME": same},
            user_dir=lambda _app: str(Path(same) / "photree"),
            site_dir=lambda _app: str(tmp_path / "site"),
        )
        assert paths == [
            Path(same) / "photree" / "config.toml",
            tmp_path / "site" / "config.toml",
        ]

    def test_xdg_is_first(self) -> None:
        paths = config_search_paths(environ={"XDG_CONFIG_HOME": "/tmp/xdg-test"})
        assert paths[0] == Path("/tmp/xdg-test/photree/config.toml")

    def test_default_xdg_when_unset(self, tmp_path: Path) -> None:
        paths = config_search_paths(environ={}, home=tmp_path)
        assert paths[0] == tmp_path / ".config" / "photree" / "config.toml"


class TestFindConfigFile:
    def test_explicit_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / "my.toml"
        cfg.write_text("", encoding="utf-8")
        assert find_config_file(str(cfg)) == cfg

    def test_explicit_path_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.toml"
        with pytest.raises(ConfigError) as exc_info:
            find_config_file(str(missing))
        assert exc_info.value.kind == ConfigErrorKind.FILE_NOT_FOUND
        assert exc_info.value.path == missing

    def test_returns_none_when_no_config(self, tmp_path: Path) -> None:
        assert _isolated_find(tmp_path) is None

    def test_finds_xdg_config(self, tmp_path: Path) -> None:
        xdg = tmp_path / "xdg"
        cfg = xdg / "photree" / "config.toml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("", encoding="utf-8")
        assert _isolated_find(tmp_path, xdg) == cfg


class TestLoadConfig:
    def test_returns_empty_config_when_no_file(self, tmp_path: Path) -> None:
        cfg = load_config(
            environ={"XDG_CONFIG_HOME": str(tmp_path / "empty-xdg")},
            home=tmp_path / "home",
            user_dir=lambda _app: str(tmp_path / "empty-user"),
            site_dir=lambda _app: str(tmp_path / "empty-site"),
        )
        assert cfg == PhotreeConfig()
        assert cfg.importer.image_capture_dir is None

    def test_parses_image_capture_dir(self, tmp_path: Path) -> None:
        cfg_file = _write_config(
            tmp_path, '[importer]\nimage-capture-dir = "/some/path"\n'
        )
        cfg = load_config(cfg_file)
        assert cfg.importer.image_capture_dir == Path("/some/path")

    def test_expands_tilde_against_home(self, tmp_path: Path) -> None:
        cfg_file = _write_config(
            tmp_path, '[importer]\nimage-capture-dir = "~/Pictures/iPhone"\n'
        )
        cfg = load_config(cfg_file, home=tmp_path / "home")
        assert cfg.importer.image_capture_dir == tmp_path / "home/Pictures/iPhone"

    def test_missing_key_returns_none(self, tmp_path: Path) -> None:
        cfg = load_config(_write_config(tmp_path, "# empty config\n"))
        assert cfg.importer.image_capture_dir is None

    def test_invalid_toml(self, tmp_path: Path) -> None:
        error = _load_error(tmp_path, "invalid = [unclosed\n")
        assert error.kind == ConfigErrorKind.INVALID_TOML
        assert error.path == tmp_path / "config.toml"

    def test_parses_single_profile(self, tmp_path: Path) -> None:
        cfg_file = _write_config(
            tmp_path,
            """\
            [exporter.profiles.mega]
            share-dir = "/mnt/share"
            share-layout = "flat"
            album-layout = "browsable-jpg"
            link-mode = "hardlink"
            """,
        )
        cfg = load_config(cfg_file)
        assert "mega" in cfg.exporter.profiles
        p = cfg.exporter.profiles["mega"]
        assert p.share_dir == Path("/mnt/share")
        assert p.share_layout == ShareDirectoryLayout.FLAT
        assert p.album_layout == AlbumShareLayout.BROWSABLE_JPG
        assert p.link_mode == LinkMode.HARDLINK

    def test_parses_multiple_profiles(self, tmp_path: Path) -> None:
        cfg_file = _write_config(
            tmp_path,
            """\
            [exporter.profiles.mega]
            share-dir = "/mnt/mega"

            [exporter.profiles.backup]
            share-dir = "/mnt/backup"
            share-layout = "albums"
            album-layout = "all"
            link-mode = "symlink"
            """,
        )
        cfg = load_config(cfg_file)
        assert len(cfg.exporter.profiles) == 2
        assert cfg.exporter.profiles["mega"].share_dir == Path("/mnt/mega")
        assert (
            cfg.exporter.profiles["backup"].share_layout == ShareDirectoryLayout.ALBUMS
        )

    def test_profiles_are_read_only(self, tmp_path: Path) -> None:
        cfg = load_config(
            _write_config(tmp_path, '[exporter.profiles.a]\nshare-dir = "/x"\n')
        )
        with pytest.raises(TypeError):
            cfg.exporter.profiles["b"] = cfg.exporter.profiles["a"]  # type: ignore[index]

    def test_profile_defaults(self, tmp_path: Path) -> None:
        cfg = load_config(
            _write_config(
                tmp_path, '[exporter.profiles.minimal]\nshare-dir = "/mnt/share"\n'
            )
        )
        p = cfg.exporter.profiles["minimal"]
        assert p.share_layout == ShareDirectoryLayout.FLAT
        assert p.album_layout == AlbumShareLayout.BROWSABLE_JPG
        assert p.link_mode == LinkMode.HARDLINK

    def test_profile_expands_tilde(self, tmp_path: Path) -> None:
        cfg_file = _write_config(
            tmp_path, '[exporter.profiles.home]\nshare-dir = "~/Shared/Albums"\n'
        )
        cfg = load_config(cfg_file, home=tmp_path / "home")
        assert cfg.exporter.profiles["home"].share_dir == (
            tmp_path / "home" / "Shared" / "Albums"
        )

    def test_profile_missing_share_dir_raises(self, tmp_path: Path) -> None:
        error = _load_error(
            tmp_path, '[exporter.profiles.bad]\nshare-layout = "flat"\n'
        )
        assert (error.kind, error.field, error.profile) == (
            ConfigErrorKind.MISSING_KEY,
            "share-dir",
            "bad",
        )

    def test_profile_invalid_share_layout_raises(self, tmp_path: Path) -> None:
        error = _load_error(
            tmp_path,
            """\
            [exporter.profiles.bad]
            share-dir = "/mnt/share"
            share-layout = "unknown"
            """,
        )
        assert (error.kind, error.field, error.value, error.profile) == (
            ConfigErrorKind.INVALID_VALUE,
            "share-layout",
            "unknown",
            "bad",
        )

    def test_profile_invalid_album_layout_raises(self, tmp_path: Path) -> None:
        error = _load_error(
            tmp_path,
            '[exporter.profiles.bad]\nshare-dir = "/mnt/share"\nalbum-layout = "nope"\n',
        )
        assert (error.kind, error.field, error.value) == (
            ConfigErrorKind.INVALID_VALUE,
            "album-layout",
            "nope",
        )

    def test_empty_profiles_section(self, tmp_path: Path) -> None:
        cfg = load_config(_write_config(tmp_path, "[exporter]\n"))
        assert cfg.exporter.profiles == {}


class TestLoadConfigTypeErrors:
    """Regression: wrong TOML types raised raw TypeError/AttributeError."""

    def test_share_dir_not_a_string(self, tmp_path: Path) -> None:
        error = _load_error(tmp_path, "[exporter.profiles.p]\nshare-dir = 5\n")
        assert (error.kind, error.field, error.value, error.profile) == (
            ConfigErrorKind.INVALID_TYPE,
            "share-dir",
            5,
            "p",
        )

    def test_importer_not_a_table(self, tmp_path: Path) -> None:
        error = _load_error(tmp_path, 'importer = "x"\n')
        assert (error.kind, error.field, error.value) == (
            ConfigErrorKind.INVALID_TYPE,
            "importer",
            "x",
        )

    def test_image_capture_dir_not_a_string(self, tmp_path: Path) -> None:
        error = _load_error(tmp_path, "[importer]\nimage-capture-dir = [1]\n")
        assert (error.kind, error.field, error.value) == (
            ConfigErrorKind.INVALID_TYPE,
            "importer.image-capture-dir",
            [1],
        )

    def test_exporter_profiles_not_a_table(self, tmp_path: Path) -> None:
        error = _load_error(tmp_path, '[exporter]\nprofiles = "x"\n')
        assert (error.kind, error.field) == (
            ConfigErrorKind.INVALID_TYPE,
            "exporter.profiles",
        )

    def test_profile_not_a_table(self, tmp_path: Path) -> None:
        error = _load_error(tmp_path, "[exporter.profiles]\np = 1\n")
        assert (error.kind, error.profile) == (ConfigErrorKind.INVALID_TYPE, "p")

    def test_link_mode_not_a_string(self, tmp_path: Path) -> None:
        error = _load_error(
            tmp_path, '[exporter.profiles.p]\nshare-dir = "/x"\nlink-mode = true\n'
        )
        assert (error.kind, error.field) == (ConfigErrorKind.INVALID_TYPE, "link-mode")
