"""The ``photree check`` command group, which its command modules register on."""

import typer

app = typer.Typer(
    name="check",
    help="System prerequisite checks.",
    no_args_is_help=True,
)
