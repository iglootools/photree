"""The ``photree gallery`` command group, which its command modules register on."""

import typer

from photree.gallery.cli import metadata

app = typer.Typer(
    name="gallery",
    help="Operations on a gallery: import, refresh, check and export its albums.",
    no_args_is_help=True,
)

app.add_typer(metadata.app)
