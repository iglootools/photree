"""The Typer app of the ``photree album`` command group."""

import typer

app = typer.Typer(
    name="album",
    help="Album management commands.",
    no_args_is_help=True,
)
