"""Export settings resolution and validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...config import load_config
from ...foundation.layout import SHARE_SENTINEL
from ...foundation.linking import LinkMode
from ...foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


class ExportSettingsErrorKind(StrEnum):
    """Why export settings could not be used."""

    UNKNOWN_PROFILE = "unknown-profile"
    NO_SHARE_DIR = "no-share-dir"
    ALBUMS_LAYOUT_NEEDS_ALL = "albums-layout-needs-all"
    MISSING_SENTINEL = "missing-sentinel"


class ExportSettingsError(ValueError):
    """Raised when export settings are invalid or incomplete.

    Carries the failure as data (*kind* plus the fields relevant to it) so the
    CLI renders paths relative to the cwd; ``str()`` is a plain fallback.
    """

    def __init__(
        self,
        kind: ExportSettingsErrorKind,
        *,
        profile: str | None = None,
        available_profiles: tuple[str, ...] = (),
        album_layout: AlbumShareLayout | None = None,
        share_dir: Path | None = None,
    ) -> None:
        super().__init__(f"invalid export settings: {kind}")
        self.kind = kind
        self.profile = profile
        self.available_profiles = available_profiles
        self.album_layout = album_layout
        self.share_dir = share_dir


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
    # Only profiles come from the config, so a searched-for config is read only
    # when a profile is named. An explicit --config is always loaded: silently
    # ignoring a path the user typed (missing file, typo) would hide the mistake.
    profile = None
    cfg = (
        load_config(config_path)
        if profile_name is not None or config_path is not None
        else None
    )
    if cfg is not None and profile_name is not None:
        profile = cfg.exporter.profiles.get(profile_name)
        if profile is None:
            raise ExportSettingsError(
                ExportSettingsErrorKind.UNKNOWN_PROFILE,
                profile=profile_name,
                available_profiles=tuple(sorted(cfg.exporter.profiles)),
            )

    resolved_share_dir = share_dir or (profile.share_dir if profile else None)
    if resolved_share_dir is None:
        raise ExportSettingsError(ExportSettingsErrorKind.NO_SHARE_DIR)

    resolved_share_layout = (
        share_layout
        or (profile.share_layout if profile else None)
        or ShareDirectoryLayout.FLAT
    )
    resolved_album_layout = (
        album_layout
        or (profile.album_layout if profile else None)
        or AlbumShareLayout.BROWSABLE_JPG
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
            ExportSettingsErrorKind.ALBUMS_LAYOUT_NEEDS_ALL,
            album_layout=settings.album_layout,
        )

    if not (settings.share_dir / SHARE_SENTINEL).exists():
        raise ExportSettingsError(
            ExportSettingsErrorKind.MISSING_SENTINEL, share_dir=settings.share_dir
        )
