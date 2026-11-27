"""
Presentation for operations over many albums.

This module holds the reports on a set of albums whose IDs stop a command,
shared by its commands; the batch import (:mod:`.importer`), export
(:mod:`.exporter`) and check (:mod:`.check`) have their own modules.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from photree.album.id import format_album_external_id
from photree.common.formatting import indent
from photree.common.fs import display_path


def format_missing_ids_report(
    albums: Sequence[Path],
    fix_command: str,
    cwd: Path,
) -> str:
    """
    Return the report of *albums* that have no ID, ending with the command to fix it.

    *fix_command* is the full command the user runs, such as
    ``photree gallery fix --id``. Plain text: print it with markup off.
    """
    return "\n".join(
        [
            "Albums with missing IDs found:",
            *(indent(str(display_path(p, cwd))) for p in albums),
            f"\nRun '{fix_command}' to generate missing album IDs.",
        ],
    )


def format_duplicate_ids_report(
    duplicates: Mapping[str, Sequence[Path]],
    cwd: Path,
) -> str:
    """
    Return the report of albums sharing an ID, ending with the command to fix it.

    *duplicates* maps each shared album ID to its albums. The suggested command
    gives new IDs to every album but the first of each ID, and names each one:
    a new ID orphans every collection and face reference to the album, so the
    album those references point to must keep its ID. Plain text: print it with
    markup off.
    """
    copies = [p for paths in duplicates.values() for p in paths[1:]]
    album_dirs = " ".join(f'--album-dir "{display_path(p, cwd)}"' for p in copies)
    fix = (
        f"\nRun 'photree albums fix --new-id {album_dirs}' to give new IDs to "
        "all but the first album of each ID."
    )
    caveat = (
        "If collections or faces refer to another of them, name the others instead."
    )
    return "\n".join(
        [
            "Duplicate album IDs found:",
            *(
                line
                for album_id, paths in duplicates.items()
                for line in [
                    indent(f"{format_album_external_id(album_id)}:"),
                    *(indent(str(display_path(p, cwd)), 2) for p in paths),
                ]
            ),
            fix,
            caveat,
        ],
    )
