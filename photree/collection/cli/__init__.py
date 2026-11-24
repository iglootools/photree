"""The ``photree collection`` command group, with every command registered on it."""

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.collection.cli import (
    check_cmd as check_cmd,
    import_cmd as import_cmd,
    init_cmd as init_cmd,
    show_cmd as show_cmd,
)
from photree.collection.cli.app import app

__all__ = ["app"]
