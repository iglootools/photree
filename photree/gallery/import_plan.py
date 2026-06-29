"""Plan a gallery import and run pre-import validation.

Shared by ``gallery import`` and ``gallery import-all``. Produces a per-album
plan (import new / reimport / skip) and collects all batch-level validation
errors so the caller can abort *before* any filesystem mutation.

Detection is hybrid (ID + name): an album is "already imported" when the
source carries an ID present in the gallery (the normal path — `album
import`/`album init` assign an ID that gallery import preserves), or — as a
fallback for an ID-less source — when its target directory already exists.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..album.naming import (
    NamingIssue,
    check_album_naming,
    check_batch_date_collisions,
    parse_album_name,
)
from ..album.store.album_discovery import has_media_sources
from ..album.store.metadata import load_album_metadata
from ..album.store.protocol import AlbumMetadata
from . import AlbumIndex
from .importer import compute_target_dir


class ImportAction(Enum):
    """What to do with a source album during import."""

    NEW = "new"
    """Not in the gallery — copy it in normally."""

    REIMPORT = "reimport"
    """Already imported and ``--reimport`` given — replace its media."""

    SKIP = "skip"
    """Already imported, no ``--reimport`` — leave it untouched."""


@dataclass(frozen=True)
class AlbumPlan:
    """Planned action for a single source album."""

    source: Path
    action: ImportAction
    target: Path
    """``<gallery>/albums/YYYY/<source-name>`` — the post-import location."""

    existing: Path | None = None
    """Current gallery directory; differs from *target* on a rename."""


@dataclass(frozen=True)
class SourceDuplicate:
    """A set of source albums in the batch sharing the same ID."""

    album_id: str
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class ClobberConflict:
    """A target name already taken by a *different* album (different ID)."""

    source: Path
    existing: Path
    source_id: str
    existing_id: str


@dataclass(frozen=True)
class GalleryImportPlan:
    """The planned outcome of importing a batch of albums into a gallery."""

    plans: tuple[AlbumPlan, ...]
    naming_errors: tuple[tuple[Path, tuple[NamingIssue, ...]], ...] = ()
    structure_errors: tuple[Path, ...] = ()
    date_collisions: tuple[tuple[str, tuple[str, ...]], ...] = ()
    source_duplicate_ids: tuple[SourceDuplicate, ...] = ()
    clobber_conflicts: tuple[ClobberConflict, ...] = ()

    @property
    def has_errors(self) -> bool:
        return bool(
            self.naming_errors
            or self.structure_errors
            or self.date_collisions
            or self.source_duplicate_ids
            or self.clobber_conflicts
        )

    @property
    def to_import(self) -> list[AlbumPlan]:
        """Plans that perform work (NEW or REIMPORT)."""
        return [
            p
            for p in self.plans
            if p.action in (ImportAction.NEW, ImportAction.REIMPORT)
        ]

    @property
    def skipped(self) -> list[AlbumPlan]:
        """Plans for already-imported albums left untouched."""
        return [p for p in self.plans if p.action is ImportAction.SKIP]


def _find_source_duplicate_ids(
    source_metas: list[tuple[Path, AlbumMetadata]],
) -> tuple[SourceDuplicate, ...]:
    """Find source albums in the batch that share the same ID."""
    sorted_sources = sorted(source_metas, key=lambda t: t[1].id)
    grouped = {
        aid: [p for p, _ in group]
        for aid, group in itertools.groupby(sorted_sources, key=lambda t: t[1].id)
    }
    return tuple(
        SourceDuplicate(album_id=aid, paths=tuple(paths))
        for aid, paths in grouped.items()
        if len(paths) > 1
    )


def _detect_collisions(
    plans: list[AlbumPlan],
    index: AlbumIndex,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Detect date collisions over the gallery's *post-import* album names.

    Reflects the final state: NEW/REIMPORT albums contribute their target
    name; existing gallery albums contribute their current name unless they
    are being replaced by a reimport (renamed to the target name).
    """
    replaced = {
        p.existing
        for p in plans
        if p.action is ImportAction.REIMPORT and p.existing is not None
    }
    final_names = [
        p.target.name
        for p in plans
        if p.action in (ImportAction.NEW, ImportAction.REIMPORT)
    ]
    final_names += [
        gpath.name for gpath in index.id_to_path.values() if gpath not in replaced
    ]
    inputs = [
        (name, parsed)
        for name in final_names
        if (parsed := parse_album_name(name)) is not None
    ]
    return check_batch_date_collisions(inputs).date_collisions


def _plan_album_import(
    source: Path,
    meta: AlbumMetadata | None,
    index: AlbumIndex,
    gallery_dir: Path,
    *,
    reimport: bool,
) -> AlbumPlan | ClobberConflict:
    """Plan the import of one validly-named album into a plan or clobber conflict."""
    target = compute_target_dir(gallery_dir, source.name)
    action = ImportAction.REIMPORT if reimport else ImportAction.SKIP

    if meta is not None and meta.id in index.id_to_path:
        return AlbumPlan(source, action, target, existing=index.id_to_path[meta.id])
    if not target.exists():
        return AlbumPlan(source, ImportAction.NEW, target)

    existing_meta = load_album_metadata(target)
    if meta is not None and existing_meta is not None and meta.id != existing_meta.id:
        return ClobberConflict(
            source=source,
            existing=target,
            source_id=meta.id,
            existing_id=existing_meta.id,
        )
    return AlbumPlan(source, action, target, existing=target)


def plan_imports(
    albums: list[Path],
    index: AlbumIndex,
    gallery_dir: Path,
    *,
    reimport: bool,
) -> GalleryImportPlan:
    """Plan the import of *albums* and collect all pre-import validation errors.

    The returned :class:`GalleryImportPlan` carries a per-album plan plus
    any naming, structure, collision, duplicate-ID, or clobber errors. The
    caller must abort (import nothing) when ``has_errors`` is true.
    """
    metas = {a: load_album_metadata(a) for a in albums}

    naming_errors = tuple(
        (a, issues) for a in albums if (issues := check_album_naming(a.name))
    )
    bad_named = {a for a, _ in naming_errors}

    structure_errors = tuple(a for a in albums if not has_media_sources(a))

    source_duplicate_ids = _find_source_duplicate_ids(
        [(a, meta) for a, meta in metas.items() if meta is not None]
    )

    # Albums with an unparseable name have no target and cannot be classified.
    classified = [
        _plan_album_import(a, metas[a], index, gallery_dir, reimport=reimport)
        for a in albums
        if a not in bad_named
    ]
    plans = [c for c in classified if isinstance(c, AlbumPlan)]
    clobber_conflicts = [c for c in classified if isinstance(c, ClobberConflict)]

    date_collisions = _detect_collisions(plans, index)

    return GalleryImportPlan(
        plans=tuple(plans),
        naming_errors=naming_errors,
        structure_errors=structure_errors,
        date_collisions=date_collisions,
        source_duplicate_ids=source_duplicate_ids,
        clobber_conflicts=tuple(clobber_conflicts),
    )
