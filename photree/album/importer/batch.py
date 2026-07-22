"""Batch import across multiple album directories."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ...common.fs import list_files
from ...fsprotocol import LinkMode
from ..jpeg import convert_single_file
from ..store.protocol import ios_import_dir, std_import_dir
from . import album_import
from .album_import import task_has_content, validate_album_import
from .tasks import discover_import_tasks, has_import_tasks

if TYPE_CHECKING:
    from ..faces.detect import FaceAnalyzerFactory


@dataclass(frozen=True)
class AlbumScan:
    """Result of scanning a parent directory for importable albums."""

    no_selection: tuple[Path, ...] = ()
    empty_selection: tuple[Path, ...] = ()
    to_import: tuple[Path, ...] = ()


@dataclass(frozen=True)
class AlbumValidation:
    """Validation result for a single album (aggregated across its tasks)."""

    album_dir: Path
    errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@dataclass
class BatchResult:
    """Result of a batch import run.

    Not frozen because it is incrementally built during the import loop.
    """

    imported: int = 0
    failed: list[tuple[Path, str]] = field(default_factory=list)
    scan: AlbumScan = AlbumScan()

    @property
    def skipped(self) -> int:
        return (
            len(self.scan.no_selection)
            + len(self.scan.empty_selection)
            + len(self.failed)
        )


def scan_albums(albums_dir: Path) -> AlbumScan:
    """Scan immediate subdirectories for importable albums."""
    subdirs = sorted(p for p in albums_dir.iterdir() if p.is_dir())
    return categorize_albums(subdirs)


def _album_has_content(album_dir: Path) -> bool:
    return any(task_has_content(t) for t in discover_import_tasks(album_dir))


def _empty_task_reason(album_dir: Path) -> str:
    """Describe why an album with ``to-import-*`` entries has nothing to import.

    Names each empty staging dir so a likely user mistake (e.g. std files placed
    directly in the dir instead of under ``orig/``) is easy to spot.
    """
    parts = [
        (
            f"{ios_import_dir(t.name)} (empty selection)"
            if t.is_ios
            else f"{std_import_dir(t.name)} (no media in orig/ or edit/)"
        )
        for t in discover_import_tasks(album_dir)
        if not task_has_content(t)
    ]
    return "; ".join(parts) if parts else "nothing to import"


def categorize_albums(album_dirs: Sequence[Path]) -> AlbumScan:
    """Categorize album directories by their ``to-import-*`` state.

    - ``no_selection``: no ``to-import-*`` entry at all.
    - ``empty_selection``: has ``to-import-*`` entries but nothing to import.
    - ``to_import``: has at least one non-empty task.
    """
    with_tasks = {d for d in album_dirs if has_import_tasks(d)}

    return AlbumScan(
        no_selection=tuple(d for d in album_dirs if d not in with_tasks),
        empty_selection=tuple(
            d for d in album_dirs if d in with_tasks and not _album_has_content(d)
        ),
        to_import=tuple(
            d for d in album_dirs if d in with_tasks and _album_has_content(d)
        ),
    )


def validate_albums(
    albums: list[Path] | tuple[Path, ...],
    image_capture_files: list[str],
) -> list[AlbumValidation]:
    """Validate all albums' import tasks against the IC file list."""
    return [
        AlbumValidation(
            album_dir=album_dir,
            errors=validate_album_import(album_dir, image_capture_files).errors,
        )
        for album_dir in albums
    ]


def run_batch_import(
    *,
    albums_dir: Path | None = None,
    album_dirs: Sequence[Path] | None = None,
    image_capture_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_importing: Callable[[str], None] | None = None,
    on_imported: Callable[[str], None] | None = None,
    on_skipped: Callable[..., None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
    on_validation_error: Callable[[str, list[str]], None] | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    max_workers: int | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
) -> BatchResult:
    """Run import for all albums with at least one non-empty import task.

    Provide exactly one of *albums_dir* (scan immediate subdirectories) or
    *album_dirs* (explicit list of album directories).

    Validates ALL albums before importing ANY. If any album fails validation,
    no imports are performed.

    Callbacks are optional hooks for the CLI layer to print status:
    - ``on_importing(album_name)`` — called before importing an album
    - ``on_imported(album_name)`` — called after a successful album import
    - ``on_skipped(album_name, reason)`` — called for each skipped album
    - ``on_error(album_name, error)`` — called when an album import fails
    - ``on_validation_error(album_name, errors)`` — called when validation fails
    """
    if (albums_dir is None) == (album_dirs is None):
        msg = "Exactly one of albums_dir or album_dirs must be provided"
        raise ValueError(msg)

    scan = (
        scan_albums(albums_dir)
        if albums_dir is not None
        else categorize_albums(album_dirs)  # type: ignore[arg-type]
    )
    result = BatchResult(scan=scan)

    for album_dir in scan.no_selection:
        if on_skipped:
            on_skipped(album_dir.name, "no to-import-{ios,std}-<name> directory")

    # A to-import-* dir that yields nothing is most likely a user mistake
    # (e.g. std files placed directly instead of under orig/) — warn, don't
    # skip silently like an album with no staging dir at all.
    for album_dir in scan.empty_selection:
        if on_skipped:
            on_skipped(album_dir.name, _empty_task_reason(album_dir), warn=True)

    # Validate all albums before importing any
    ic_files = list_files(image_capture_dir) if scan.to_import else []
    validations = validate_albums(scan.to_import, ic_files)
    failed_validations = [v for v in validations if not v.success]
    if failed_validations:
        for v in failed_validations:
            if on_validation_error:
                on_validation_error(v.album_dir.name, list(v.errors))
        return result

    # All validations passed — proceed with imports
    for album_dir in scan.to_import:
        if on_importing:
            on_importing(album_dir.name)
        try:
            import_result = album_import.run_import(
                album_dir=album_dir,
                image_capture_dir=image_capture_dir,
                link_mode=link_mode,
                dry_run=dry_run,
                convert_file=convert_file,
                max_workers=max_workers,
                analyzer_factory=analyzer_factory,
            )
            if import_result.unprocessed:
                msg = f"unprocessed selection files: {', '.join(import_result.unprocessed)}"
                result.failed.append((album_dir, msg))
                if on_error:
                    on_error(album_dir.name, msg)
            else:
                result.imported += 1
                if on_imported:
                    on_imported(album_dir.name)
        except (FileNotFoundError, ValueError) as exc:
            result.failed.append((album_dir, str(exc)))
            if on_error:
                on_error(album_dir.name, str(exc))

    return result
