import typer

app = typer.Typer(
    name="collections",
    help="Batch operations on multiple collections.",
    no_args_is_help=True,
)

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from . import check_cmd as check_cmd
from . import import_cmd as import_cmd
