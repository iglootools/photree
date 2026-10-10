"""Configuration data types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from ..foundation.linking import LinkMode
from ..foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


class ConfigErrorKind(StrEnum):
    """What is wrong with the configuration."""

    FILE_NOT_FOUND = "file-not-found"
    INVALID_TOML = "invalid-toml"
    MISSING_KEY = "missing-key"
    INVALID_TYPE = "invalid-type"
    INVALID_VALUE = "invalid-value"


class ConfigError(Exception):
    """Raised when configuration is invalid.

    Carries the failure as structured data — *kind*, the config *path*, the
    TOML *field* (dotted key; the bare key inside a profile), the offending
    *value*, the exporter *profile* name, and what was *expected* — so tests
    and callers can inspect it; ``str()`` renders the human message. A plain
    class rather than a frozen dataclass: Python assigns ``__traceback__`` on
    raise.
    """

    def __init__(
        self,
        kind: ConfigErrorKind,
        *,
        path: Path | None = None,
        field: str | None = None,
        value: object = None,
        profile: str | None = None,
        expected: str | None = None,
    ) -> None:
        self.kind = kind
        self.path = path
        self.field = field
        self.value = value
        self.profile = profile
        self.expected = expected
        super().__init__(self.__str__())

    def __str__(self) -> str:
        where = f' in profile "{self.profile}"' if self.profile is not None else ""
        match self.kind:
            case ConfigErrorKind.FILE_NOT_FOUND:
                return f"Config file not found: {self.path}"
            case ConfigErrorKind.INVALID_TOML:
                return f"Invalid TOML in {self.path}: {self.expected}"
            case ConfigErrorKind.MISSING_KEY:
                return f'Missing required key "{self.field}"{where}'
            case ConfigErrorKind.INVALID_TYPE:
                return (
                    f'Invalid type for "{self.field}"{where}: expected'
                    f" {self.expected}, got {type(self.value).__name__}"
                    f" ({self.value!r})"
                )
            case ConfigErrorKind.INVALID_VALUE:
                return (
                    f'Invalid {self.field} "{self.value}"{where}.'
                    f" Valid values: {self.expected}"
                )


@dataclass(frozen=True)
class ImporterConfig:
    """Configuration for Image Capture import (``photree album import``)."""

    image_capture_dir: Path | None = None


@dataclass(frozen=True)
class ExporterProfile:
    """A named exporter profile."""

    share_dir: Path
    share_layout: ShareDirectoryLayout = ShareDirectoryLayout.FLAT
    album_layout: AlbumShareLayout = AlbumShareLayout.BROWSABLE_JPG
    link_mode: LinkMode = LinkMode.HARDLINK


@dataclass(frozen=True)
class ExporterConfig:
    """Configuration for album export (``photree album export``)."""

    # Read-only view: a frozen dataclass must not expose a mutable dict.
    profiles: Mapping[str, ExporterProfile] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class PhotreeConfig:
    """Application configuration."""

    importer: ImporterConfig = ImporterConfig()
    exporter: ExporterConfig = ExporterConfig()
