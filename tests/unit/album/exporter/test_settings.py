from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType

import pytest

from photree.album.exporter.settings import (
    ExportSettingsError,
    ExportSettingsErrorKind,
    ResolvedExportSettings,
    resolve_export_settings,
    validate_export_settings,
)
from photree.config import ExporterConfig, ExporterProfile, PhotreeConfig
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout

_MEGA = ExporterProfile(
    share_dir=Path("/mega"),
    share_layout=ShareDirectoryLayout.ALBUMS,
    album_layout=AlbumShareLayout.ALL,
    link_mode=LinkMode.SYMLINK,
)


def _loader(
    loaded: list[str | None],
    **profiles: ExporterProfile,
) -> Callable[[str | None], PhotreeConfig]:
    """Return a ``load`` that records each config path and serves *profiles*."""

    def load(config_path: str | None) -> PhotreeConfig:
        loaded.append(config_path)
        return PhotreeConfig(
            exporter=ExporterConfig(profiles=MappingProxyType(profiles)),
        )

    return load


def _resolve(
    load: Callable[[str | None], PhotreeConfig],
    *,
    profile_name: str | None = None,
    share_dir: Path | None = None,
    share_layout: ShareDirectoryLayout | None = None,
    album_layout: AlbumShareLayout | None = None,
    link_mode: LinkMode | None = None,
    config_path: str | None = None,
) -> ResolvedExportSettings:
    return resolve_export_settings(
        profile_name=profile_name,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config_path=config_path,
        load=load,
    )


class TestResolveExportSettings:
    def test_profile_supplies_every_setting(self) -> None:
        settings = _resolve(_loader([], mega=_MEGA), profile_name="mega")

        assert settings == ResolvedExportSettings(
            share_dir=Path("/mega"),
            share_layout=ShareDirectoryLayout.ALBUMS,
            album_layout=AlbumShareLayout.ALL,
            link_mode=LinkMode.SYMLINK,
        )

    def test_flags_override_the_profile(self) -> None:
        settings = _resolve(
            _loader([], mega=_MEGA),
            profile_name="mega",
            share_dir=Path("/elsewhere"),
            share_layout=ShareDirectoryLayout.BY_MONTH,
            album_layout=AlbumShareLayout.ARCHIVE,
            link_mode=LinkMode.COPY,
        )

        assert settings == ResolvedExportSettings(
            share_dir=Path("/elsewhere"),
            share_layout=ShareDirectoryLayout.BY_MONTH,
            album_layout=AlbumShareLayout.ARCHIVE,
            link_mode=LinkMode.COPY,
        )

    def test_one_flag_overrides_only_its_setting(self) -> None:
        settings = _resolve(
            _loader([], mega=_MEGA),
            profile_name="mega",
            link_mode=LinkMode.COPY,
        )

        assert settings == ResolvedExportSettings(
            share_dir=Path("/mega"),
            share_layout=ShareDirectoryLayout.ALBUMS,
            album_layout=AlbumShareLayout.ALL,
            link_mode=LinkMode.COPY,
        )

    def test_defaults_apply_without_a_profile(self) -> None:
        settings = _resolve(_loader([]), share_dir=Path("/share"))

        assert settings == ResolvedExportSettings(
            share_dir=Path("/share"),
            share_layout=ShareDirectoryLayout.FLAT,
            album_layout=AlbumShareLayout.BROWSABLE_JPG,
            link_mode=LinkMode.HARDLINK,
        )

    def test_config_is_not_read_without_a_profile_or_config(self) -> None:
        loaded: list[str | None] = []

        _resolve(_loader(loaded), share_dir=Path("/share"))

        assert loaded == []

    def test_explicit_config_is_read_without_a_profile(self) -> None:
        loaded: list[str | None] = []

        settings = _resolve(
            _loader(loaded, mega=_MEGA),
            share_dir=Path("/share"),
            config_path="my.toml",
        )

        assert loaded == ["my.toml"]
        # No profile is named, so none of the config's profiles applies.
        assert settings.album_layout == AlbumShareLayout.BROWSABLE_JPG

    def test_unknown_profile_lists_the_available_ones(self) -> None:
        with pytest.raises(ExportSettingsError) as info:
            _resolve(
                _loader([], nas=_MEGA, mega=_MEGA),
                profile_name="usb",
                share_dir=Path("/share"),
            )

        assert info.value.kind == ExportSettingsErrorKind.UNKNOWN_PROFILE
        assert info.value.profile == "usb"
        assert info.value.available_profiles == ("mega", "nas")

    def test_no_share_dir_is_an_error(self) -> None:
        with pytest.raises(ExportSettingsError) as info:
            _resolve(_loader([]))

        assert info.value.kind == ExportSettingsErrorKind.NO_SHARE_DIR


class TestValidateExportSettings:
    @pytest.mark.parametrize(
        "album_layout",
        [
            AlbumShareLayout.BROWSABLE_JPG,
            AlbumShareLayout.BROWSABLE,
            AlbumShareLayout.ARCHIVE,
        ],
    )
    def test_albums_share_layout_needs_the_all_album_layout(
        self,
        album_layout: AlbumShareLayout,
    ) -> None:
        with pytest.raises(ExportSettingsError) as info:
            validate_export_settings(
                ResolvedExportSettings(
                    share_dir=Path("/nonexistent/share"),
                    share_layout=ShareDirectoryLayout.ALBUMS,
                    album_layout=album_layout,
                    link_mode=LinkMode.HARDLINK,
                ),
            )

        assert info.value.kind == ExportSettingsErrorKind.ALBUMS_LAYOUT_NEEDS_ALL
        assert info.value.album_layout == album_layout

    def test_share_dir_without_sentinel_is_an_error(self) -> None:
        with pytest.raises(ExportSettingsError) as info:
            validate_export_settings(
                ResolvedExportSettings(
                    share_dir=Path("/nonexistent/share"),
                    share_layout=ShareDirectoryLayout.ALBUMS,
                    album_layout=AlbumShareLayout.ALL,
                    link_mode=LinkMode.HARDLINK,
                ),
            )

        assert info.value.kind == ExportSettingsErrorKind.MISSING_SENTINEL
        assert info.value.share_dir == Path("/nonexistent/share")
