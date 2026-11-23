"""Reports on a set of albums whose IDs stop a command, shared by its commands."""

from collections.abc import Sequence
from pathlib import Path

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
