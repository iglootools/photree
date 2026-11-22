"""The ``photree gallery metadata`` command group, which ``set_cmd`` registers on."""

import typer

app = typer.Typer(
    name="metadata",
    help="Gallery metadata management.",
    no_args_is_help=True,
)
