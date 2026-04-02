"""TOML configuration loading with platform-aware search paths.

Search order (first existing file wins):

1. Explicit ``--config`` path
2. ``$XDG_CONFIG_HOME/photree/config.toml`` (defaults to ``~/.config/photree/config.toml``)
3. Platform user config dir (macOS: ``~/Library/Application Support/photree/config.toml``)
4. Platform site config dir (macOS: ``/Library/Application Support/photree/config.toml``)
"""

from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path

from platformdirs import site_config_dir, user_config_dir

from ..fsprotocol import AlbumShareLayout, ShareDirectoryLayout
from ..fsprotocol import LinkMode
from .protocol import (
    ConfigError,
    ExporterConfig,
    ExporterProfile,
    ImporterConfig,
    PhotreeConfig,
)

_APP = "photree"
_FILENAME = "config.toml"

_EMPTY_CONFIG = PhotreeConfig()


def config_search_paths() -> list[Path]:
    """Config file search paths in priority order.

    Order: XDG > platform user config > platform site config.
    On Linux, XDG and platform user config resolve to the same path
    and are deduped (dict.fromkeys preserves insertion order).
    Added explicitly so that ~/.config/photree/config.toml works on macOS
    (for which user_config_dir defaults to ~/Library/Application Support/photree).
    """
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    candidates = [
        Path(xdg) / _APP / _FILENAME,
        Path(user_config_dir(_APP)) / _FILENAME,
        Path(site_config_dir(_APP)) / _FILENAME,
    ]
    return list(dict.fromkeys(candidates))


def find_config_file(config_path: str | None = None) -> Path | None:
    """Find the configuration file using the search order.

    Returns ``None`` when no config file is found (config is optional).
    Raises :class:`ConfigError` when an explicit *config_path* does not exist.
    """
    if config_path is not None:
        p = Path(config_path)
        if not p.is_file():
            raise ConfigError(f"Config file not found: {config_path}")
        else:
            return p
    else:
        search = config_search_paths()
        return next((p for p in search if p.is_file()), None)


def _parse_enum[E: StrEnum](
    value: str, enum_cls: type[E], field_name: str, profile_name: str
) -> E:
    """Parse a string into a StrEnum, raising ConfigError on invalid values."""
    try:
        return enum_cls(value)
    except ValueError:
        valid = ", ".join(f'"{e.value}"' for e in enum_cls)
        raise ConfigError(
            f'Invalid {field_name} "{value}" in profile "{profile_name}". '
            f"Valid values: {valid}"
        ) from None


def _parse_profile(name: str, section: object) -> ExporterProfile:
    """Parse a single ``[exporter.profiles.<name>]`` table."""
    if not isinstance(section, dict):
        raise ConfigError(f'Profile "{name}" must be a TOML table')

    share_dir_str = section.get("share-dir")
    if share_dir_str is None:
        raise ConfigError(f'Profile "{name}" is missing required key "share-dir"')

    return ExporterProfile(
        share_dir=Path(os.path.expanduser(share_dir_str)),
        share_layout=_parse_enum(
            section.get("share-layout", ShareDirectoryLayout.FLAT),
            ShareDirectoryLayout,
            "share-layout",
            name,
        ),
        album_layout=_parse_enum(
            section.get("album-layout", AlbumShareLayout.MAIN_JPG),
            AlbumShareLayout,
            "album-layout",
            name,
        ),
        link_mode=_parse_enum(
            section.get("link-mode", LinkMode.HARDLINK),
            LinkMode,
            "link-mode",
            name,
        ),
    )


def _parse_profiles(raw_profiles: dict[str, object]) -> dict[str, ExporterProfile]:
    """Parse the ``[exporter.profiles.*]`` sub-tables."""
    return {
        name: _parse_profile(name, section) for name, section in raw_profiles.items()
    }


def load_config(config_path: str | None = None) -> PhotreeConfig:
    """Load configuration from a TOML file.

    Returns a default (empty) config when no config file is found.
    """
    path = find_config_file(config_path)
    if path is None:
        return _EMPTY_CONFIG

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {path}: {e}") from e

    import_section = raw.get("importer", {})
    image_capture_dir_str = import_section.get("image-capture-dir")
    image_capture_dir = (
        Path(os.path.expanduser(image_capture_dir_str))
        if image_capture_dir_str is not None
        else None
    )

    export_section = raw.get("exporter", {})
    raw_profiles = export_section.get("profiles", {})
    profiles = _parse_profiles(raw_profiles)

    return PhotreeConfig(
        importer=ImporterConfig(image_capture_dir=image_capture_dir),
        exporter=ExporterConfig(profiles=profiles),
    )
