"""The ``photree collection`` command group, which its command modules register on."""

import typer

from photree.collection.cli import metadata

app = typer.Typer(
    name="collection",
    help="Collection management commands.",
    no_args_is_help=True,
)

app.add_typer(metadata.app)
