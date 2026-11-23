"""
The photree configuration: importer settings, exporter profiles and its errors.

Each field of a TOML table's dataclass is one key of that table: the key is
the field name in kebab-case, and its ``metadata`` holds what the
configuration reference shows for it (``build-scripts/configdocs.py``
generates the field tables in ``docs/config-reference.md`` from these
classes).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


class ConfigErrorKind(StrEnum):
    """What is wrong with the configuration."""

    FILE_NOT_FOUND = "file-not-found"
    UNREADABLE_FILE = "unreadable-file"
    INVALID_TOML = "invalid-toml"
    MISSING_KEY = "missing-key"
    INVALID_TYPE = "invalid-type"
    INVALID_VALUE = "invalid-value"


class ConfigError(Exception):
    """
    Raised when configuration is invalid.

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
        """Build the error from its kind and whichever details that kind reports."""
        self.kind = kind
        self.path = path
        self.field = field
        self.value = value
        self.profile = profile
        self.expected = expected
        super().__init__(self.__str__())

    def __str__(self) -> str:
        """Return the message for this error's kind, naming the profile if any."""
        where = f' in profile "{self.profile}"' if self.profile is not None else ""
        match self.kind:
            case ConfigErrorKind.FILE_NOT_FOUND:
                return f"Config file not found: {self.path}"
            case ConfigErrorKind.UNREADABLE_FILE:
                return f"Cannot read config file {self.path}: {self.expected}"
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


def toml_key(field_name: str) -> str:
    """Return the TOML key a config dataclass field is written as (kebab-case)."""
    return field_name.replace("_", "-")


def _doc(description: str, *, shown_default: str | None = None) -> dict[str, str]:
    """
    Build a config field's ``metadata`` for the configuration reference.

    *shown_default* replaces the dataclass default in the reference when the
    real default is applied elsewhere (the dataclass holds ``None``).
    """
    return {
        "description": description,
        **({"shown_default": shown_default} if shown_default is not None else {}),
    }


@dataclass(frozen=True)
class ImporterConfig:
    """Configuration for Image Capture import (``photree album import``)."""

    image_capture_dir: Path | None = field(
        default=None,
        metadata=_doc(
            "Directory where macOS Image Capture saves the files it imports from"
            " the phone. macOS names it after the device, with a typographic"
            " apostrophe (`\u2019`), not an ASCII `'`.",
            shown_default="~/Pictures/iPhone",
        ),
    )


@dataclass(frozen=True)
class ExporterProfile:
    """One named export destination: its share directory, layouts and link mode."""

    share_dir: Path = field(metadata=_doc("Base directory to export into."))
    share_layout: ShareDirectoryLayout = field(
        default=ShareDirectoryLayout.FLAT,
        metadata=_doc(
            "How albums are arranged under `share-dir`: all side by side"
            " (`flat`), by year (`albums`), or by month (`by-month`).",
        ),
    )
    album_layout: AlbumShareLayout = field(
        default=AlbumShareLayout.BROWSABLE_JPG,
        metadata=_doc("Which of an album's directories are exported."),
    )
    link_mode: LinkMode = field(
        default=LinkMode.HARDLINK,
        metadata=_doc("How exported files reference the gallery's files."),
    )


@dataclass(frozen=True)
class ExporterConfig:
    """Configuration for album export (``photree album export``)."""

    # Read-only view: a frozen dataclass must not expose a mutable dict.
    profiles: Mapping[str, ExporterProfile] = field(
        default_factory=lambda: MappingProxyType({}),
    )


@dataclass(frozen=True)
class PhotreeConfig:
    """The whole photree configuration: importer and exporter settings."""

    importer: ImporterConfig = ImporterConfig()
    exporter: ExporterConfig = ExporterConfig()
