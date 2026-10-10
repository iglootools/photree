"""Names of the import staging entries an album carries.

Import staging entries are named ``to-import-{ios,std}-<media-source>``. Each
targets a specific media source: iOS sources use the directory (and an
optional sibling ``.csv``) as a selection list matched against Image Capture;
std sources place their files directly under ``orig/`` and ``edit/``.

Shared by the importer (which consumes the entries) and the album check
(which must not flag them as unexpected directories), so it lives at the
album level rather than inside either.
"""

from __future__ import annotations

import re

from .store.media_source import MediaSourceType

TO_IMPORT_PREFIX = "to-import-"

STAGING_DIR_RE = re.compile(rf"^{re.escape(TO_IMPORT_PREFIX)}(ios|std)-(.+)$")
"""``to-import-<kind>-<name>``; group 1 is the kind, group 2 the source name."""

STAGING_CSV_RE = re.compile(rf"^{re.escape(TO_IMPORT_PREFIX)}ios-(.+)\.csv$")
"""``to-import-ios-<name>.csv``; group 1 is the source name."""


def ios_import_dir(name: str) -> str:
    """Return the iOS import staging dir name (e.g. ``to-import-ios-main``)."""
    return f"{TO_IMPORT_PREFIX}{MediaSourceType.IOS}-{name}"


def ios_import_csv(name: str) -> str:
    """Return the iOS import CSV name (e.g. ``to-import-ios-main.csv``)."""
    return f"{ios_import_dir(name)}.csv"


def std_import_dir(name: str) -> str:
    """Return the std import staging dir name (e.g. ``to-import-std-nelu``)."""
    return f"{TO_IMPORT_PREFIX}{MediaSourceType.STD}-{name}"


def is_import_staging_dir(name: str) -> bool:
    """Return True for a ``to-import-{ios,std}-<name>`` staging directory."""
    return name.startswith((f"{TO_IMPORT_PREFIX}ios-", f"{TO_IMPORT_PREFIX}std-"))
