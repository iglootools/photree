"""Batch album rename planning from CSV input."""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..album.id import ALBUM_ID_PREFIX, InvalidExternalIdError, parse_external_id
from ..album.naming import ParsedAlbumName, parse_album_name, reconstruct_name


@dataclass(frozen=True)
class RenameAction:
    """A planned album directory rename."""

    album_path: Path
    current_name: str
    new_name: str

    @property
    def target(self) -> Path:
        return self.album_path.parent / self.new_name


class RenamePlanErrorKind(StrEnum):
    """Why a CSV row cannot be turned into a rename."""

    EMPTY_ID = "empty-id"
    INVALID_ID = "invalid-id"
    ID_NOT_FOUND = "id-not-found"
    UNPARSEABLE_NAME = "unparseable-name"
    EMPTY_TITLE = "empty-title"


@dataclass(frozen=True)
class RenamePlanError:
    """An invalid CSV row.

    ``row`` is the 1-based data row (the header is not counted).
    ``album_name`` is set when the row's album was found.
    """

    kind: RenamePlanErrorKind
    row: int
    external_id: str
    album_name: str | None = None


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _has_mutable_changes(
    parsed: ParsedAlbumName,
    series: str | None,
    title: str,
    location: str | None,
) -> bool:
    return (
        _nfc(parsed.series or "") != _nfc(series or "")
        or _nfc(parsed.title) != _nfc(title)
        or _nfc(parsed.location or "") != _nfc(location or "")
    )


def _parse_album_id(external_id: str) -> str | None:
    try:
        return parse_external_id(external_id, ALBUM_ID_PREFIX)
    except InvalidExternalIdError:
        return None


def _locate(
    row_number: int, external_id: str, index: Mapping[str, Path]
) -> Path | RenamePlanError:
    """The album a row refers to, or why it cannot be found."""
    if not external_id:
        return RenamePlanError(RenamePlanErrorKind.EMPTY_ID, row_number, "")
    internal_id = _parse_album_id(external_id)
    if internal_id is None:
        return RenamePlanError(RenamePlanErrorKind.INVALID_ID, row_number, external_id)
    album_path = index.get(internal_id)
    return (
        album_path
        if album_path is not None
        else RenamePlanError(RenamePlanErrorKind.ID_NOT_FOUND, row_number, external_id)
    )


def _plan_row(
    row_number: int, row: Mapping[str, str], index: Mapping[str, Path]
) -> RenameAction | RenamePlanError | None:
    """Process a single CSV row.

    Returns a :class:`RenameAction` when a rename is needed, a
    :class:`RenamePlanError` when the row is invalid, or ``None`` when no
    change is needed.
    """
    external_id = (row.get("id") or "").strip()
    located = _locate(row_number, external_id, index)
    if isinstance(located, RenamePlanError):
        return located

    parsed = parse_album_name(located.name)
    csv_series = (row.get("series") or "").strip() or None
    csv_title = (row.get("title") or "").strip()
    csv_location = (row.get("location") or "").strip() or None
    match parsed:
        case None:
            kind = RenamePlanErrorKind.UNPARSEABLE_NAME
            return RenamePlanError(kind, row_number, external_id, located.name)
        case _ if not csv_title:
            kind = RenamePlanErrorKind.EMPTY_TITLE
            return RenamePlanError(kind, row_number, external_id, located.name)
        case _ if not _has_mutable_changes(parsed, csv_series, csv_title, csv_location):
            return None
        case _:
            new_name = reconstruct_name(
                ParsedAlbumName(
                    date=parsed.date,
                    part=parsed.part,
                    private=parsed.private,
                    series=csv_series,
                    title=csv_title,
                    location=csv_location,
                )
            )
            return RenameAction(located, located.name, new_name)


def plan_renames_from_csv(
    rows: list[dict[str, str]],
    index: Mapping[str, Path],
) -> tuple[tuple[RenameAction, ...], tuple[RenamePlanError, ...]]:
    """Plan album renames from CSV rows against the album index.

    Each row must contain ``id``, ``series``, ``title``, ``location`` columns.
    Other columns are ignored.  Immutable fields (``date``, ``part``,
    ``private``) come from the current on-disk album name.

    Returns ``(actions, errors)``.
    """
    results = [_plan_row(n, row, index) for n, row in enumerate(rows, start=1)]
    actions = tuple(r for r in results if isinstance(r, RenameAction))
    errors = tuple(r for r in results if isinstance(r, RenamePlanError))
    return actions, errors


class RenameCollisionError(ValueError):
    """Raised when a rename target conflicts with an existing directory
    or with another planned rename's target."""

    def __init__(self, current_name: str, new_name: str) -> None:
        self.current_name = current_name
        self.new_name = new_name
        super().__init__(
            f"Collision: {current_name} → {new_name} conflicts with existing directory"
        )


def check_rename_collisions(actions: tuple[RenameAction, ...]) -> None:
    """Check for target directory collisions among planned renames.

    Raises :class:`RenameCollisionError` if any target conflicts with an
    existing directory that is not itself being renamed, or if two renames
    share a target. Swaps (A↔B) and chains (A→B→C) are fine:
    :func:`execute_renames` moves everything aside before placing it.
    """
    renamed_resolved = {a.album_path.resolve() for a in actions}
    target_counts = Counter(a.target.resolve() for a in actions)
    collision = next(
        (
            action
            for action in actions
            if target_counts[action.target.resolve()] > 1
            or (
                action.target.exists()
                and action.target.resolve() != action.album_path.resolve()
                and action.target.resolve() not in renamed_resolved
            )
        ),
        None,
    )
    if collision is not None:
        raise RenameCollisionError(collision.current_name, collision.new_name)


# ---------------------------------------------------------------------------
# Execution (two-phase, so swaps and chains cannot trip over each other)
# ---------------------------------------------------------------------------

_STAGING_PREFIX = ".photree-renaming-"


class RenamePhase(StrEnum):
    """Where a rename run failed."""

    PREFLIGHT = "preflight"  # a staging name was already taken
    STAGE = "stage"  # moving an album aside to its staging name
    FINALIZE = "finalize"  # moving a staged album to its new name


@dataclass(frozen=True)
class RenameFailure:
    """Why a rename run stopped.

    Every rename done before the failure is rolled back (best effort);
    ``stranded`` lists the paths that could not be put back and need manual
    attention (empty when the rollback was complete).
    """

    action: RenameAction
    phase: RenamePhase
    reason: str
    stranded: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RenameExecution:
    """Outcome of :func:`execute_renames`."""

    renamed: int
    failure: RenameFailure | None = None


def _rename_all(moves: list[tuple[Path, Path]]) -> tuple[int, OSError | None]:
    """Perform the moves in order, stopping at the first failure.

    Returns how many moves were done and the error that stopped the run.
    """
    # A per-item try/except that must stop the run cannot be a comprehension.
    for done, (src, dst) in enumerate(moves):
        try:
            src.rename(dst)
        except OSError as exc:
            return done, exc
    return len(moves), None


def _undo(moves: list[tuple[Path, Path]]) -> tuple[Path, ...]:
    """Reverse each ``(src, dst)`` move; return the ``dst`` paths left behind."""
    return tuple(dst for src, dst in moves if _rename_all([(dst, src)])[1] is not None)


def _reason(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


def _failed_staging(
    actions: tuple[RenameAction, ...], temps: list[Path], staged: int, exc: OSError
) -> RenameExecution:
    sources = [a.album_path for a in actions]
    stranded = _undo(list(zip(sources[:staged], temps[:staged])))
    failure = RenameFailure(actions[staged], RenamePhase.STAGE, _reason(exc), stranded)
    return RenameExecution(renamed=0, failure=failure)


def _failed_finalizing(
    actions: tuple[RenameAction, ...], temps: list[Path], done: int, exc: OSError
) -> RenameExecution:
    finals = [a.target for a in actions]
    unrestored = _undo(list(zip(temps[:done], finals[:done])))
    # Albums whose final name could not be undone are not in staging either.
    restorable = [
        (a.album_path, temp)
        for a, temp, final in zip(actions, temps, finals)
        if final not in unrestored
    ]
    stranded = (*unrestored, *_undo(restorable))
    failure = RenameFailure(actions[done], RenamePhase.FINALIZE, _reason(exc), stranded)
    return RenameExecution(renamed=0, failure=failure)


def execute_renames(actions: tuple[RenameAction, ...]) -> RenameExecution:
    """Execute planned renames, all or nothing (best effort).

    Every album is first moved to a hidden staging name in its own parent,
    then to its new name. Renaming in place would fail on a swap (A↔B) or a
    chain (A→B, B→C) as soon as a target is still occupied by an album that
    has not moved yet, leaving the gallery half-renamed.
    """
    temps = [
        a.album_path.parent / f"{_STAGING_PREFIX}{i}" for i, a in enumerate(actions)
    ]
    occupied = next((i for i, t in enumerate(temps) if t.exists()), None)
    if occupied is not None:
        failure = RenameFailure(
            actions[occupied],
            RenamePhase.PREFLIGHT,
            "staging path already exists",
            (temps[occupied],),
        )
        return RenameExecution(renamed=0, failure=failure)

    staged, exc = _rename_all([(a.album_path, t) for a, t in zip(actions, temps)])
    if exc is not None:
        return _failed_staging(actions, temps, staged, exc)
    done, exc = _rename_all([(t, a.target) for a, t in zip(actions, temps)])
    if exc is not None:
        return _failed_finalizing(actions, temps, done, exc)
    return RenameExecution(renamed=len(actions))
