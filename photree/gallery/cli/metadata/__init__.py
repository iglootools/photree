"""The ``photree gallery metadata`` command group, with its commands registered."""

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.gallery.cli.metadata import set_cmd as set_cmd
from photree.gallery.cli.metadata.app import app

__all__ = ["app"]
