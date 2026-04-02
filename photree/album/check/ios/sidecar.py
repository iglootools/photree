"""AAE sidecar validation checks.

Detects missing and orphan AAE sidecars in orig and edit directories
of iOS media sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....common.fs import file_ext, list_files
from ...store.media_sources import ios_img_number, ios_is_media
from ...store.protocol import (
    SIDECAR_EXTENSIONS,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SidecarCheck:
    """Result of checking AAE sidecars in orig and edit directories."""

    missing_sidecars: tuple[str, ...]
    orphan_sidecars: tuple[str, ...]


# ---------------------------------------------------------------------------
# Check function
# ---------------------------------------------------------------------------


def check_sidecars(
    orig_dir: Path,
    edit_dir: Path,
) -> SidecarCheck:
    """Check for missing and orphan AAE sidecars in orig and edit directories."""
    orig_files = set(list_files(orig_dir))
    edit_files = set(list_files(edit_dir))

    orig_media_numbers = {ios_img_number(f) for f in orig_files if ios_is_media(f)}
    edit_media_numbers = {
        ios_img_number(f)
        for f in edit_files
        if ios_is_media(f) and f.upper().startswith("IMG_E")
    }

    missing_sidecars = tuple(
        [
            # Each HEIC in orig should have an AAE sidecar
            *[
                f"{f} has no AAE sidecar in {orig_dir.name}/"
                for f in sorted(orig_files)
                if file_ext(f) == ".heic"
                and f"IMG_{ios_img_number(f)}.AAE" not in orig_files
            ],
            # Each edited media file should have an O-prefixed AAE sidecar
            *[
                f"{f} has no O-prefixed AAE sidecar in {edit_dir.name}/"
                for f in sorted(edit_files)
                if ios_is_media(f)
                and f.upper().startswith("IMG_E")
                and f"IMG_O{ios_img_number(f)}.AAE" not in edit_files
            ],
        ]
    )

    orphan_sidecars = tuple(
        [
            # Orphan AAE sidecars in orig (no matching media file)
            *[
                f"{f} has no matching media file in {orig_dir.name}/"
                for f in sorted(orig_files)
                if file_ext(f) in SIDECAR_EXTENSIONS
                and ios_img_number(f) not in orig_media_numbers
            ],
            # Orphan O-prefixed AAE sidecars in edit (no matching edited media)
            *[
                f"{f} has no matching edited media file in {edit_dir.name}/"
                for f in sorted(edit_files)
                if file_ext(f) in SIDECAR_EXTENSIONS
                and f.upper().startswith("IMG_O")
                and ios_img_number(f) not in edit_media_numbers
            ],
        ]
    )

    return SidecarCheck(
        missing_sidecars=missing_sidecars,
        orphan_sidecars=orphan_sidecars,
    )
