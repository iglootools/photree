"""TOML configuration loading with platform-aware search paths.

Search order (first existing file wins):

1. Explicit ``--config`` path
2. ``$XDG_CONFIG_HOME/photree/config.toml`` (defaults to ``~/.config/photree/config.toml``)
3. Platform user config dir (macOS: ``~/Library/Application Support/photree/config.toml``)
4. Platform site config dir (macOS: ``/Library/Application Support/photree/config.toml``)

The process environment, home directory, and platformdirs lookups are
parameters (defaulting to the real ones) so tests pass values instead of
patching module state.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from platformdirs import site_config_dir, user_config_dir

from ..fsprotocol import AlbumShareLayout, LinkMode, ShareDirectoryLayout
from .protocol import (
    ConfigError,
    ConfigErrorKind,
    ExporterConfig,
    ExporterProfile,
    ImporterConfig,
    PhotreeConfig,
)

_APP = "photree"
_FILENAME = "config.toml"

_EMPTY_CONFIG = PhotreeConfig()

# ``platformdirs`` lookup signature: app name -> directory.
ConfigDirFn = Callable[[str], str]


def config_search_paths(
    *,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
    user_dir: ConfigDirFn = user_config_dir,
    site_dir: ConfigDirFn = site_config_dir,
) -> list[Path]:
    """Config file search paths in priority order.

    Order: XDG > platform user config > platform site config.
    On Linux, XDG and platform user config resolve to the same path
    and are deduped (dict.fromkeys preserves insertion order).
    Added explicitly so that ~/.config/photree/config.toml works on macOS
    (for which user_config_dir defaults to ~/Library/Application Support/photree).
    *home* defaults to :meth:`Path.home`.
    """
    resolved_home = home if home is not None else Path.home()
    xdg = environ.get("XDG_CONFIG_HOME", str(resolved_home / ".config"))
    candidates = [
        Path(xdg) / _APP / _FILENAME,
        Path(user_dir(_APP)) / _FILENAME,
        Path(site_dir(_APP)) / _FILENAME,
    ]
    return list(dict.fromkeys(candidates))


def find_config_file(
    config_path: str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
    user_dir: ConfigDirFn = user_config_dir,
    site_dir: ConfigDirFn = site_config_dir,
) -> Path | None:
    """Find the configuration file using the search order.

    Returns ``None`` when no config file is found (config is optional).
    Raises :class:`ConfigError` when an explicit *config_path* does not exist.
    """
    if config_path is not None:
        p = Path(config_path)
        if not p.is_file():
            raise ConfigError(ConfigErrorKind.FILE_NOT_FOUND, path=p)
        else:
            return p
    else:
        search = config_search_paths(
            environ=environ, home=home, user_dir=user_dir, site_dir=site_dir
        )
        return next((p for p in search if p.is_file()), None)


# ---------------------------------------------------------------------------
# Typed accessors — every TOML value is checked before use, so a wrong type
# surfaces as a ConfigError (exit 2) rather than a TypeError/AttributeError.
# ---------------------------------------------------------------------------


def _table(
    raw: Mapping[str, object], key: str, *, field: str, profile: str | None = None
) -> Mapping[str, object]:
    """Return sub-table *key* of *raw* (empty when absent)."""
    return _as_table(raw.get(key, {}), field=field, profile=profile)


def _as_table(
    value: object, *, field: str, profile: str | None = None
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(
            ConfigErrorKind.INVALID_TYPE,
            field=field,
            value=value,
            profile=profile,
            expected="a TOML table",
        )
    else:
        return value


def _optional_str(
    raw: Mapping[str, object], key: str, *, field: str, profile: str | None = None
) -> str | None:
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        raise ConfigError(
            ConfigErrorKind.INVALID_TYPE,
            field=field,
            value=value,
            profile=profile,
            expected="a string",
        )
    else:
        return value


def _required_str(raw: Mapping[str, object], key: str, *, profile: str) -> str:
    value = _optional_str(raw, key, field=key, profile=profile)
    if value is None:
        raise ConfigError(ConfigErrorKind.MISSING_KEY, field=key, profile=profile)
    else:
        return value


def _enum[E: StrEnum](
    raw: Mapping[str, object], key: str, enum_cls: type[E], default: E, profile: str
) -> E:
    """Parse optional key *key* into *enum_cls*, raising ConfigError if invalid."""
    value = _optional_str(raw, key, field=key, profile=profile)
    try:
        return enum_cls(value) if value is not None else default
    except ValueError:
        raise ConfigError(
            ConfigErrorKind.INVALID_VALUE,
            field=key,
            value=value,
            profile=profile,
            expected=", ".join(f'"{e.value}"' for e in enum_cls),
        ) from None


def _expand_user(value: str, home: Path) -> Path:
    """Expand a leading ``~`` against *home* (``~user`` falls back to the OS)."""
    match value.partition("/"):
        case ("~", _, rest):
            return home / rest
        case _:
            return Path(os.path.expanduser(value))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _parse_profile(name: str, section: object, home: Path) -> ExporterProfile:
    """Parse a single ``[exporter.profiles.<name>]`` table."""
    table = _as_table(section, field="exporter.profiles", profile=name)
    return ExporterProfile(
        share_dir=_expand_user(_required_str(table, "share-dir", profile=name), home),
        share_layout=_enum(
            table, "share-layout", ShareDirectoryLayout, ShareDirectoryLayout.FLAT, name
        ),
        album_layout=_enum(
            table,
            "album-layout",
            AlbumShareLayout,
            AlbumShareLayout.BROWSABLE_JPG,
            name,
        ),
        link_mode=_enum(table, "link-mode", LinkMode, LinkMode.HARDLINK, name),
    )


def _parse_importer(raw: Mapping[str, object], home: Path) -> ImporterConfig:
    section = _table(raw, "importer", field="importer")
    image_capture_dir = _optional_str(
        section, "image-capture-dir", field="importer.image-capture-dir"
    )
    return ImporterConfig(
        image_capture_dir=(
            _expand_user(image_capture_dir, home)
            if image_capture_dir is not None
            else None
        )
    )


def _parse_exporter(raw: Mapping[str, object], home: Path) -> ExporterConfig:
    section = _table(raw, "exporter", field="exporter")
    profiles = _table(section, "profiles", field="exporter.profiles")
    return ExporterConfig(
        profiles=MappingProxyType(
            {
                name: _parse_profile(name, profile, home)
                for name, profile in profiles.items()
            }
        )
    )


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(
            ConfigErrorKind.INVALID_TOML, path=path, expected=str(e)
        ) from e


def load_config(
    config_path: str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
    user_dir: ConfigDirFn = user_config_dir,
    site_dir: ConfigDirFn = site_config_dir,
) -> PhotreeConfig:
    """Load configuration from a TOML file.

    Returns a default (empty) config when no config file is found. Raises
    :class:`ConfigError` for a missing explicit file, invalid TOML, or a
    value of the wrong type or outside its allowed set.
    """
    path = find_config_file(
        config_path, environ=environ, home=home, user_dir=user_dir, site_dir=site_dir
    )
    if path is None:
        return _EMPTY_CONFIG
    else:
        raw = _read_toml(path)
        resolved_home = home if home is not None else Path.home()
        return PhotreeConfig(
            importer=_parse_importer(raw, resolved_home),
            exporter=_parse_exporter(raw, resolved_home),
        )
