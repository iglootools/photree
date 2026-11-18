import typer

app = typer.Typer(
    name="collection",
    help="Collection management commands.",
    no_args_is_help=True,
)

from . import metadata

app.add_typer(metadata.app)

from . import (  # noqa: F401 — imported for command registration side effects
    check_cmd,
    import_cmd,
    init_cmd,
    show_cmd,
)
