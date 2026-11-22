"""The ``photree albums`` command group, which its command modules register on."""

import typer

app = typer.Typer(
    name="albums",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)
