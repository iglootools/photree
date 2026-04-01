"""Export settings resolution and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from ...config import load_config
from ...fs import (
    AlbumShareLayout,
    LinkMode,
    SHARE_SENTINEL,
    ShareDirectoryLayout,
)


class ExportSettingsError(ValueError):
    """Raised when export settings are invalid or incomplete."""


@dataclass(frozen=True)
class ResolvedExportSettings:
    """Fully resolved export settings."""

    share_dir: Path
    share_layout: ShareDirectoryLayout
    album_layout: AlbumShareLayout
    link_mode: LinkMode


def resolve_export_settings(
    *,
    profile_name: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config_path: str | None,
) -> ResolvedExportSettings:
    """Resolve export settings: CLI flags > profile > defaults.

    Raises :class:`ExportSettingsError` on invalid or incomplete settings.
    Raises :class:`~photree.config.ConfigError` on config file errors.
    """
    profile = None
    if profile_name is not None:
        cfg = load_config(config_path)
        profile = cfg.exporter.profiles.get(profile_name)
        if profile is None:
            available = ", ".join(sorted(cfg.exporter.profiles)) or "(none)"
            raise ExportSettingsError(
                f'Unknown profile "{profile_name}". Available profiles: {available}'
            )

    resolved_share_dir = share_dir or (profile.share_dir if profile else None)
    if resolved_share_dir is None:
        raise ExportSettingsError(
            "No --share-dir specified and no profile selected."
        )

    resolved_share_layout = (
        share_layout
        or (profile.share_layout if profile else None)
        or ShareDirectoryLayout.FLAT
    )
    resolved_album_layout = (
        album_layout
        or (profile.album_layout if profile else None)
        or AlbumShareLayout.MAIN_JPG
    )
    resolved_link_mode = (
        link_mode or (profile.link_mode if profile else None) or LinkMode.HARDLINK
    )

    return ResolvedExportSettings(
        share_dir=resolved_share_dir,
        share_layout=resolved_share_layout,
        album_layout=resolved_album_layout,
        link_mode=resolved_link_mode,
    )


def validate_export_settings(settings: ResolvedExportSettings) -> None:
    """Validate resolved settings, checking sentinel and layout constraints.

    Raises :class:`ExportSettingsError` on validation failure.
    """
    if (
        settings.share_layout == ShareDirectoryLayout.ALBUMS
        and settings.album_layout != AlbumShareLayout.ALL
    ):
        raise ExportSettingsError(
            f'The "albums" share layout requires --album-layout=all, '
            f"but got --album-layout={settings.album_layout.value}."
        )

    sentinel = settings.share_dir / SHARE_SENTINEL
    if not sentinel.exists():
        indent = " " * 2
        raise ExportSettingsError(
            dedent(f"""\
                Share directory does not contain a {SHARE_SENTINEL} sentinel file: \
                {settings.share_dir}

                To initialize a share directory, ensure the volume is mounted
                and create the sentinel file:
                {indent}touch {sentinel}""")
        )
