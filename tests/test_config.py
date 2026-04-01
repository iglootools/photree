"""Tests for photree.config module."""

from pathlib import Path

import pytest

from photree.config import (
    ConfigError,
    PhotreeConfig,
    config_search_paths,
    find_config_file,
    load_config,
)
from photree.fs import AlbumShareLayout, LinkMode, ShareDirectoryLayout


class TestConfigSearchPaths:
    def test_returns_deduplicated_paths(self) -> None:
        paths = config_search_paths()
        assert len(paths) == len(set(paths))

    def test_xdg_is_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-test")
        paths = config_search_paths()
        assert paths[0] == Path("/tmp/xdg-test/photree/config.toml")

    def test_default_xdg_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        paths = config_search_paths()
        assert paths[0] == Path.home() / ".config" / "photree" / "config.toml"


class TestFindConfigFile:
    def test_explicit_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / "my.toml"
        cfg.write_text("")
        assert find_config_file(str(cfg)) == cfg

    def test_explicit_path_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            find_config_file(str(tmp_path / "missing.toml"))

    def test_returns_none_when_no_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))
        # Patch platformdirs to also point to empty dirs
        monkeypatch.setattr(
            "photree.config.user_config_dir", lambda _app: str(tmp_path / "empty-user")
        )
        monkeypatch.setattr(
            "photree.config.site_config_dir", lambda _app: str(tmp_path / "empty-site")
        )
        assert find_config_file() is None

    def test_finds_xdg_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        xdg = tmp_path / "xdg"
        cfg = xdg / "photree" / "config.toml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        assert find_config_file() == cfg


class TestLoadConfig:
    def test_returns_empty_config_when_no_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
        monkeypatch.setattr(
            "photree.config.user_config_dir", lambda _app: str(tmp_path / "empty-user")
        )
        monkeypatch.setattr(
            "photree.config.site_config_dir", lambda _app: str(tmp_path / "empty-site")
        )
        cfg = load_config()
        assert cfg == PhotreeConfig()
        assert cfg.importer.image_capture_dir is None

    def test_parses_image_capture_dir(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[importer]\nimage-capture-dir = "/some/path"\n')
        cfg = load_config(str(cfg_file))
        assert cfg.importer.image_capture_dir == Path("/some/path")

    def test_expands_tilde(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[importer]\nimage-capture-dir = "~/Pictures/iPhone"\n')
        cfg = load_config(str(cfg_file))
        assert cfg.importer.image_capture_dir == Path.home() / "Pictures" / "iPhone"

    def test_missing_key_returns_none(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("# empty config\n")
        cfg = load_config(str(cfg_file))
        assert cfg.importer.image_capture_dir is None

    def test_invalid_toml(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("invalid = [unclosed\n")
        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_config(str(cfg_file))

    def test_parses_single_profile(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            "[exporter.profiles.mega]\n"
            'share-dir = "/mnt/share"\n'
            'share-layout = "flat"\n'
            'album-layout = "main-jpg"\n'
            'link-mode = "hardlink"\n'
        )
        cfg = load_config(str(cfg_file))
        assert "mega" in cfg.exporter.profiles
        p = cfg.exporter.profiles["mega"]
        assert p.share_dir == Path("/mnt/share")
        assert p.share_layout == ShareDirectoryLayout.FLAT
        assert p.album_layout == AlbumShareLayout.MAIN_JPG
        assert p.link_mode == LinkMode.HARDLINK

    def test_parses_multiple_profiles(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            "[exporter.profiles.mega]\n"
            'share-dir = "/mnt/mega"\n'
            "\n"
            "[exporter.profiles.backup]\n"
            'share-dir = "/mnt/backup"\n'
            'share-layout = "albums"\n'
            'album-layout = "all"\n'
            'link-mode = "symlink"\n'
        )
        cfg = load_config(str(cfg_file))
        assert len(cfg.exporter.profiles) == 2
        assert cfg.exporter.profiles["mega"].share_dir == Path("/mnt/mega")
        assert (
            cfg.exporter.profiles["backup"].share_layout == ShareDirectoryLayout.ALBUMS
        )

    def test_profile_defaults(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[exporter.profiles.minimal]\nshare-dir = "/mnt/share"\n')
        cfg = load_config(str(cfg_file))
        p = cfg.exporter.profiles["minimal"]
        assert p.share_layout == ShareDirectoryLayout.FLAT
        assert p.album_layout == AlbumShareLayout.MAIN_JPG
        assert p.link_mode == LinkMode.HARDLINK

    def test_profile_expands_tilde(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[exporter.profiles.home]\nshare-dir = "~/Shared/Albums"\n')
        cfg = load_config(str(cfg_file))
        assert (
            cfg.exporter.profiles["home"].share_dir == Path.home() / "Shared" / "Albums"
        )

    def test_profile_missing_share_dir_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[exporter.profiles.bad]\nshare-layout = "flat"\n')
        with pytest.raises(ConfigError, match='missing required key "share-dir"'):
            load_config(str(cfg_file))

    def test_profile_invalid_share_layout_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            "[exporter.profiles.bad]\n"
            'share-dir = "/mnt/share"\n'
            'share-layout = "unknown"\n'
        )
        with pytest.raises(ConfigError, match='Invalid share-layout "unknown"'):
            load_config(str(cfg_file))

    def test_profile_invalid_album_layout_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            '[exporter.profiles.bad]\nshare-dir = "/mnt/share"\nalbum-layout = "nope"\n'
        )
        with pytest.raises(ConfigError, match='Invalid album-layout "nope"'):
            load_config(str(cfg_file))

    def test_empty_profiles_section(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("[exporter]\n")
        cfg = load_config(str(cfg_file))
        assert cfg.exporter.profiles == {}
