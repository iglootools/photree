"""The root ``photree`` command group, with every command group added."""

import importlib.metadata
from typing import Annotated

import typer

from photree.album import cli as album
from photree.albums import cli as albums
from photree.check import cli as check
from photree.collection import cli as collection
from photree.collections import cli as collections
from photree.demo.cli import cmd as demo
from photree.gallery import cli as gallery


def _version_callback(*, value: bool) -> None:
    if value:
        typer.echo(importlib.metadata.version("photree"))
        raise typer.Exit


app = typer.Typer(
    name="photree",
    help="Manage photos in a directory tree",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Manage photos in a directory tree."""


app.add_typer(album.app)
app.add_typer(albums.app)
app.add_typer(check.app)
app.add_typer(collection.app)
app.add_typer(collections.app)
app.add_typer(demo.app)
app.add_typer(gallery.app)
