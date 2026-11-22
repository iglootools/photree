"""The ``photree check`` command group, with every command registered."""

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.check.cli import cmd as cmd
from photree.check.cli.app import app

__all__ = ["app"]
