"""The ``photree gallery`` command group, which its command modules register on."""

import typer

from photree.gallery.cli import metadata

app = typer.Typer(
    name="gallery",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)

app.add_typer(metadata.app)
