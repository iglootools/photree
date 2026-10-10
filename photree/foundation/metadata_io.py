"""Metadata errors and YAML I/O.

Every ``.photree/*.yaml`` store distinguishes *absent* (``None``: nothing
has been written yet) from *present but unreadable* (an error). Folding the
two together is how a truncated ``album.yaml`` used to make ``album init``
mint a fresh ID and silently orphan every collection reference to the old
one.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError


class InvalidMetadataError(ValueError):
    """A metadata file exists but its content cannot be used.

    Carries the path and reason as structured data so the CLI can render the
    path with ``display_path`` and tests can assert on fields, not prose.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid metadata in {path}: {reason}")


def load_yaml_mapping(path: Path) -> dict[str, object] | None:
    """Read a YAML mapping, or ``None`` if *path* does not exist.

    Raises :class:`InvalidMetadataError` when the file exists but is not
    parseable YAML or does not hold a mapping (empty and truncated files
    included).
    """
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InvalidMetadataError(path, f"not valid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise InvalidMetadataError(
            path, f"expected a YAML mapping, got {type(raw).__name__}"
        )
    return raw


def validate_metadata[M: BaseModel](path: Path, model_cls: type[M], raw: object) -> M:
    """Validate *raw* against *model_cls*, reporting failures against *path*."""
    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        raise InvalidMetadataError(path, str(exc)) from exc


def write_yaml(path: Path, data: object) -> None:
    """Write *data* as block-style YAML in UTF-8, preserving key order."""
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
