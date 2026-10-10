"""Match series runs to existing implicit collections, preserving their IDs.

Three tiers, in order: exact name, same title with overlapping members (the
date range changed), identical members (the series title changed).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..naming import (
    parse_collection_name,
)
from ..store.protocol import (
    CollectionLifecycle,
)
from .scan import ExistingCollection
from .series import SeriesTarget


@dataclass(frozen=True)
class ImplicitIndex:
    """Lookup structures for matching series groups to existing implicit collections."""

    implicit: tuple[ExistingCollection, ...]
    by_name: Mapping[str, ExistingCollection]
    by_title: Mapping[str, tuple[ExistingCollection, ...]]

    @staticmethod
    def build(existing: tuple[ExistingCollection, ...]) -> ImplicitIndex:
        implicit = tuple(
            col
            for col in existing
            if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
        )
        titled = [(parse_collection_name(col.name).title, col) for col in implicit]
        return ImplicitIndex(
            implicit=implicit,
            by_name={col.name: col for col in implicit},
            by_title={
                title: tuple(col for t, col in titled if t == title)
                for title in dict.fromkeys(t for t, _ in titled)
            },
        )


def _find_by_title_overlap(
    candidates: tuple[ExistingCollection, ...],
    active_ids: frozenset[str],
    album_ids: tuple[str, ...],
) -> ExistingCollection | None:
    """Find an implicit collection with the same title that shares members.

    Used when the date range changed (albums added/removed) but the series
    title is the same. Prefers the candidate with the most overlap (the first
    one on a tie).
    """
    album_set = set(album_ids)
    best = max(
        (
            (len(album_set & set(col.metadata.albums)), col)
            for col in candidates
            if col.metadata.id not in active_ids
        ),
        key=lambda scored: scored[0],
        default=None,
    )
    return best[1] if best is not None and best[0] > 0 else None


def _find_renamed_implicit(
    implicit: tuple[ExistingCollection, ...],
    active_ids: frozenset[str],
    album_ids: tuple[str, ...],
) -> ExistingCollection | None:
    """Find an implicit collection whose members match (rename detection)."""
    album_set = set(album_ids)
    return next(
        (
            col
            for col in implicit
            if col.metadata.id not in active_ids
            and set(col.metadata.albums) == album_set
        ),
        None,
    )


def _match_existing(
    target: SeriesTarget, index: ImplicitIndex, active_ids: frozenset[str]
) -> ExistingCollection | None:
    """Match a target to an existing implicit collection not yet claimed.

    1. Exact name match. 2. Same title, overlapping members (date range
    changed). 3. Identical members (series title changed).
    """
    by_name = index.by_name.get(target.collection_name)
    return (
        (
            by_name
            if by_name is not None and by_name.metadata.id not in active_ids
            else None
        )
        or _find_by_title_overlap(
            index.by_title.get(target.series_title, ()), active_ids, target.album_ids
        )
        or _find_renamed_implicit(index.implicit, active_ids, target.album_ids)
    )


@dataclass(frozen=True)
class GroupMatch:
    target: SeriesTarget
    existing: ExistingCollection | None
    conflict: bool = False
    """Another, earlier series run already claimed this collection name."""


def match_groups(targets: list[SeriesTarget], index: ImplicitIndex) -> list[GroupMatch]:
    """Match every target, each existing collection at most once.

    A documented accumulator exception (loop-carried state): which IDs and
    names are already claimed depends on every earlier match, so the loop
    threads them through. Without it, two same-date runs of one series
    (A, B, A) build the same name and the second silently overwrites the
    first's collection.
    """
    matches: list[GroupMatch] = []
    claimed_ids: frozenset[str] = frozenset()
    claimed_names: frozenset[str] = frozenset()
    for target in targets:
        group_match = (
            GroupMatch(target, None, conflict=True)
            if target.collection_name in claimed_names
            else GroupMatch(target, _match_existing(target, index, claimed_ids))
        )
        claimed_names |= {target.collection_name}
        if group_match.existing is not None:
            claimed_ids |= {group_match.existing.metadata.id}
        matches.append(group_match)
    return matches
