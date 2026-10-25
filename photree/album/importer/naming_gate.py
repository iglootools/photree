"""Light check (naming + date collisions) run before ``album import``.

The same check gates ``gallery import``, which tests collisions against the
gallery's albums. An album being filled outside the gallery cannot see those,
so here collisions are tested against the albums next to it (its siblings,
as ``album check`` does). For an album already in a gallery, its siblings are
the gallery albums of its year, which is every album a single-day date can
collide with.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..naming import (
    NamingIssue,
    check_album_naming,
    check_batch_date_collisions,
    parse_album_name,
)
from ..store.album_discovery import discover_albums


@dataclass(frozen=True)
class ImportNamingCheck:
    """Naming issues and date collisions blocking an import."""

    naming_errors: tuple[tuple[Path, tuple[NamingIssue, ...]], ...] = ()
    date_collisions: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def success(self) -> bool:
        return not self.naming_errors and not self.date_collisions


def _peers(albums: Sequence[Path]) -> list[Path]:
    """The albums being imported plus their sibling albums, without duplicates."""
    parents = dict.fromkeys(a.parent for a in albums)
    return list(
        dict.fromkeys(
            [*albums, *(peer for parent in parents for peer in discover_albums(parent))]
        )
    )


def _date_collisions(
    albums: Sequence[Path],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Collisions among *albums* and their siblings that involve one of *albums*.

    Collisions between siblings alone are left to ``albums check``: they are
    not this import's to block.
    """
    names = {a.name for a in albums}
    collisions = check_batch_date_collisions(
        [
            (p.name, parsed)
            for p in _peers(albums)
            if (parsed := parse_album_name(p.name)) is not None
        ]
    ).date_collisions
    return tuple(c for c in collisions if names & set(c[1]))


def check_import_naming(albums: Sequence[Path]) -> ImportNamingCheck:
    """Run the light check over the albums about to be imported."""
    return ImportNamingCheck(
        naming_errors=tuple(
            (a, issues) for a in albums if (issues := check_album_naming(a.name))
        ),
        date_collisions=_date_collisions(albums),
    )
