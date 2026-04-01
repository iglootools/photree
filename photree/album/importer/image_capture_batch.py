"""Batch import from Image Capture across multiple album directories."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ...fs import SELECTION_DIR, LinkMode
from ..jpeg import convert_single_file
from . import image_capture
from .image_capture import (
    ImportPlan,
    ValidationError,
    _list_files,
    plan_import,
    validate_import_plan,
)


@dataclass(frozen=True)
class AlbumScan:
    """Result of scanning a parent directory for importable albums."""

    no_selection: tuple[Path, ...] = ()
    empty_selection: tuple[Path, ...] = ()
    to_import: tuple[Path, ...] = ()


@dataclass(frozen=True)
class AlbumValidation:
    """Validation result for a single album."""

    album_dir: Path
    plan: ImportPlan
    errors: tuple[ValidationError, ...] = ()

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


def categorize_albums(album_dirs: Sequence[Path]) -> AlbumScan:
    """Categorize album directories by their selection-folder state."""
    return AlbumScan(
        no_selection=tuple(d for d in album_dirs if not (d / SELECTION_DIR).is_dir()),
        empty_selection=tuple(
            d
            for d in album_dirs
            if (d / SELECTION_DIR).is_dir() and not any((d / SELECTION_DIR).iterdir())
        ),
        to_import=tuple(
            d
            for d in album_dirs
            if (d / SELECTION_DIR).is_dir() and any((d / SELECTION_DIR).iterdir())
        ),
    )


def _validate_album(album_dir: Path, image_capture_files: list[str]) -> AlbumValidation:
    """Validate a single album against the IC file list."""
    selection_files = _list_files(album_dir / SELECTION_DIR)
    plan = plan_import(selection_files, image_capture_files)
    errors = validate_import_plan(plan)
    return AlbumValidation(album_dir=album_dir, plan=plan, errors=tuple(errors))


def validate_albums(
    albums: list[Path] | tuple[Path, ...],
    image_capture_files: list[str],
) -> list[AlbumValidation]:
    """Validate all albums against the IC directory."""
    return [_validate_album(album_dir, image_capture_files) for album_dir in albums]


def run_batch_import(
    *,
    albums_dir: Path | None = None,
    album_dirs: Sequence[Path] | None = None,
    image_capture_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_importing: Callable[[str], None] | None = None,
    on_imported: Callable[[str], None] | None = None,
    on_skipped: Callable[[str, str], None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
    on_validation_error: Callable[[str, list[ValidationError]], None] | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
) -> BatchResult:
    """Run import for all albums with a non-empty selection directory.

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
            on_skipped(album_dir.name, f"no {SELECTION_DIR}/ folder")

    for album_dir in scan.empty_selection:
        if on_skipped:
            on_skipped(album_dir.name, f"{SELECTION_DIR}/ is empty")

    # Validate all albums before importing any
    ic_files = _list_files(image_capture_dir) if scan.to_import else []
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
            import_result = image_capture.run_import(
                album_dir=album_dir,
                image_capture_dir=image_capture_dir,
                link_mode=link_mode,
                dry_run=dry_run,
                convert_file=convert_file,
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
        except FileNotFoundError as exc:
            result.failed.append((album_dir, str(exc)))
            if on_error:
                on_error(album_dir.name, str(exc))

    return result
