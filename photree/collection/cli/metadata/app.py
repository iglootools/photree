"""The ``photree collection metadata`` command group, which ``set_cmd`` registers on."""

import typer

app = typer.Typer(
    name="metadata",
    help="Collection metadata management.",
    no_args_is_help=True,
)
