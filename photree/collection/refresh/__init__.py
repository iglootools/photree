"""Refresh implicit collections and smart collection members.

Called by ``gallery refresh`` to:
1. Detect album series → create/update/rename/delete implicit collections
2. Materialize smart collection members by date range
3. Sync album titles with collection lifecycle changes

Each stage plans its changes first and validates them (target names free,
no two groups claiming one name) before touching the filesystem, so a
refresh that reports an error has not half-applied its stage. Dry runs
follow the same plan, applied in memory only.

Stages live in their own modules: ``scan`` (phase 1), ``title_sync``
(phase 2), ``series`` / ``implicit_match`` / ``implicit`` (phase 3) and
``smart`` (phase 4); ``result`` holds the result and error types. This
module is the orchestrator.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from ..id import generate_collection_id
from .implicit import ImplicitChanges, refresh_implicit_collections
from .result import CollectionRefreshResult
from .scan import scan_existing_collections, scan_gallery
from .smart import refresh_smart_collections
from .title_sync import TitleSync, sync_album_titles

# Refresh stage names (for progress callbacks)
STAGE_SCAN_ALBUMS = "scan-albums"
STAGE_TITLE_SYNC = "title-sync"
STAGE_IMPLICIT_REFRESH = "implicit-refresh"
STAGE_SMART_REFRESH = "smart-refresh"

REFRESH_STAGES = (
    STAGE_SCAN_ALBUMS,
    STAGE_TITLE_SYNC,
    STAGE_IMPLICIT_REFRESH,
    STAGE_SMART_REFRESH,
)


@dataclass(frozen=True)
class _Notifier:
    on_stage_start: Callable[[str], None] | None
    on_stage_end: Callable[[str], None] | None

    @contextmanager
    def stage(self, name: str) -> Generator[None, None, None]:
        if self.on_stage_start is not None:
            self.on_stage_start(name)
        yield
        if self.on_stage_end is not None:
            self.on_stage_end(name)


def _partial_result(
    implicit: ImplicitChanges, sync: TitleSync
) -> CollectionRefreshResult:
    """The result as of the end of the implicit stage."""
    return CollectionRefreshResult(
        created=implicit.created,
        updated=implicit.updated,
        renamed=implicit.renamed,
        deleted=implicit.deleted,
        album_renames=sync.renames,
        errors=implicit.errors,
    )


def refresh_collections(
    gallery_dir: Path,
    *,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    new_id: Callable[[], str] = generate_collection_id,
) -> CollectionRefreshResult:
    """Refresh all collections in the gallery.

    1. Scan and validate album names (light check, no EXIF)
    2. Sync album titles with existing collection lifecycle changes
    3. Refresh implicit collections from album series
    4. Materialize smart collection members
    """
    notifier = _Notifier(on_stage_start, on_stage_end)
    with notifier.stage(STAGE_SCAN_ALBUMS):
        scan = scan_gallery(gallery_dir)
    if scan.errors:
        return CollectionRefreshResult(errors=scan.errors)

    with notifier.stage(STAGE_TITLE_SYNC):
        sync = sync_album_titles(scan.albums, scan.collections, dry_run=dry_run)
    if sync.errors:
        return CollectionRefreshResult(errors=sync.errors)

    with notifier.stage(STAGE_IMPLICIT_REFRESH):
        implicit = refresh_implicit_collections(
            gallery_dir, sync.albums, scan.collections, dry_run=dry_run, new_id=new_id
        )
    partial = _partial_result(implicit, sync)
    if implicit.errors:
        return partial

    with notifier.stage(STAGE_SMART_REFRESH):
        # Re-scan: the implicit stage may have renamed or created collections.
        collections, rescan_errors = scan_existing_collections(gallery_dir)
        smart_updated = refresh_smart_collections(
            sync.albums, collections, dry_run=dry_run
        )
    return replace(
        partial,
        updated=(*partial.updated, *smart_updated),
        errors=rescan_errors,
    )
