"""The ``photree collections`` command group, which its command modules register on."""

import typer

app = typer.Typer(
    name="collections",
    help="Batch operations on multiple collections.",
    no_args_is_help=True,
)
