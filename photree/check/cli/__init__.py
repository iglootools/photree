import typer

app = typer.Typer(
    name="check",
    help="System prerequisite checks.",
    no_args_is_help=True,
)

# Imported for its side effect: the module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from . import cmd as cmd
