"""Output sink shared by the ``list*`` wrappers.

``--output/-o`` applies to every format: text listings are written to the
file just like CSV ones. (It used to be silently ignored in text mode, so
``list -o out.txt`` printed to the terminal and left no file.)
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

import typer

from ....clihelpers.csvout import csv_output


def write_text(lines: Iterable[str], output_file: Path | None) -> None:
    """Write text lines to *output_file*, or echo them to stdout."""
    all_lines = list(lines)
    text = "".join(f"{line}\n" for line in all_lines)
    match output_file:
        case None:
            typer.echo(text, nl=False)
        case _:
            output_file.write_text(text, encoding="utf-8")


def write_csv(
    header: Sequence[str], rows: Iterable[Sequence[str]], output_file: Path | None
) -> None:
    """Write a CSV (header first) to *output_file*, or to stdout."""
    with csv_output(output_file) as out:
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)
