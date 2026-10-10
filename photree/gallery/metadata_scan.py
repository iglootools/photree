"""Metadata reads for gallery-wide scans."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def read_or_none[T](load: Callable[[Path], T | None], directory: Path) -> T | None:
    """Load *directory*'s metadata, mapping unreadable content to ``None``.

    Only for scans whose callers turn ``None`` into a per-item error (never
    into "absent, create a fresh one"): one corrupt file is then reported
    alongside every other problem instead of aborting the scan on the first.
    """
    try:
        return load(directory)
    except ValueError:
        # InvalidMetadataError, and pydantic's ValidationError raised by
        # loaders that predate it, are both ValueErrors.
        return None
