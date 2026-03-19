"""CLI app definition."""

import importlib.metadata
from typing import Annotated, Optional

import typer


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
