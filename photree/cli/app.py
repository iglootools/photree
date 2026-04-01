"""CLI app and sub-app definitions."""

import importlib.metadata
from typing import Annotated, Optional

import typer

from ..album.cli import album_app
from ..albums.cli import albums_app
from ..check.cli.cmd import check_cmd
from ..demo.cli.cmd import demo_app
from ..gallery.cli import gallery_app


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(importlib.metadata.version("photree"))
        raise typer.Exit()


app = typer.Typer(
    name="photree",
    help="Manage photos in a directory tree",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def _main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    pass


app.command("check")(check_cmd)
app.add_typer(album_app)
app.add_typer(albums_app)
app.add_typer(demo_app)
app.add_typer(gallery_app)
