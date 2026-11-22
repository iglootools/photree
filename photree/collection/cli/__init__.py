import typer

app = typer.Typer(
    name="collection",
    help="Collection management commands.",
    no_args_is_help=True,
)

from . import metadata

app.add_typer(metadata.app)

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from . import check_cmd as check_cmd
from . import import_cmd as import_cmd
from . import init_cmd as init_cmd
from . import show_cmd as show_cmd
