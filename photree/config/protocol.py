"""Configuration data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..album.exporter.protocol import AlbumShareLayout, ShareDirectoryLayout
from ..fsprotocol import LinkMode


class ConfigError(Exception):
    """Raised when configuration is invalid."""


@dataclass(frozen=True)
class ImporterConfig:
    """Configuration for Image Capture import (``photree album import``)."""

    image_capture_dir: Path | None = None


@dataclass(frozen=True)
class ExporterProfile:
    """A named exporter profile."""

    share_dir: Path
    share_layout: ShareDirectoryLayout = ShareDirectoryLayout.FLAT
    album_layout: AlbumShareLayout = AlbumShareLayout.MAIN_JPG
    link_mode: LinkMode = LinkMode.HARDLINK


@dataclass(frozen=True)
class ExporterConfig:
    """Configuration for album export (``photree album export``)."""

    profiles: dict[str, ExporterProfile] = field(default_factory=dict)


@dataclass(frozen=True)
class PhotreeConfig:
    """Application configuration."""

    importer: ImporterConfig = ImporterConfig()
    exporter: ExporterConfig = ExporterConfig()
