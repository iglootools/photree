"""Resolution and validation of the export settings: share dir and layouts."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.config import PhotreeConfig, load_config
from photree.foundation.layout import SHARE_SENTINEL
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


class ExportSettingsErrorKind(StrEnum):
    """Why export settings are invalid, one kind per error message."""

    UNKNOWN_PROFILE = "unknown-profile"
    NO_SHARE_DIR = "no-share-dir"
    ALBUMS_LAYOUT_NEEDS_ALL = "albums-layout-needs-all"
    MISSING_SENTINEL = "missing-sentinel"


def is_usage_error(kind: ExportSettingsErrorKind) -> bool:
    """
    Return whether *kind* is wrong whatever is on disk.

    A usage error (exit 2) is fixed by changing the flags or the config; only
    a missing sentinel depends on the share directory (exit 1), and may be
    fixed by mounting the volume.
    """
    return kind != ExportSettingsErrorKind.MISSING_SENTINEL


class ExportSettingsError(ValueError):
    """
    Invalid export settings.

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
        """Build the error from its *kind* and the fields that kind reports."""
        super().__init__(f"invalid export settings: {kind}")
        self.kind = kind
        self.profile = profile
        self.available_profiles = available_profiles
        self.album_layout = album_layout
        self.share_dir = share_dir


@dataclass(frozen=True)
class ResolvedExportSettings:
    """The export settings after merging CLI flags, the profile and the defaults."""

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
    config_path: Path | None,
    load: Callable[[Path | None], PhotreeConfig] = load_config,
) -> ResolvedExportSettings:
    """
    Resolve export settings: CLI flags > profile > defaults.

    *load* loads the config file (the CLI passes its runtime's).

    Raises :class:`ExportSettingsError` on invalid or incomplete settings.
    Raises :class:`~photree.config.ConfigError` on config file errors.
    """
    # Only profiles come from the config, so a searched-for config is read only
    # when a profile is named. An explicit --config is always loaded: silently
    # ignoring a path the user typed (missing file, typo) would hide the mistake.
    profile = None
    loaded_config = (
        load(config_path)
        if profile_name is not None or config_path is not None
        else None
    )
    if loaded_config is not None and profile_name is not None:
        profile = loaded_config.exporter.profiles.get(profile_name)
        if profile is None:
            raise ExportSettingsError(
                ExportSettingsErrorKind.UNKNOWN_PROFILE,
                profile=profile_name,
                available_profiles=tuple(sorted(loaded_config.exporter.profiles)),
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
    """Raise :class:`ExportSettingsError` on validation failure."""
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
            ExportSettingsErrorKind.MISSING_SENTINEL,
            share_dir=settings.share_dir,
        )
