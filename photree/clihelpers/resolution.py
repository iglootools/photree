"""Directory resolution helpers shared by every command surface.

``resolve_gallery_or_exit`` lives here rather than in ``gallery/cli/ops.py``
because ``collection`` and ``collections`` commands need it too, and importing
it from ``gallery`` made those packages depend on ``gallery`` — which depends
on them back. It is a generic CLI concern (turn a resolution failure into a
clean exit), not a gallery one.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..fsprotocol import resolve_gallery_dir
from .console import err_console


def resolve_gallery_or_exit(gallery_dir: Path | None) -> Path:
    """Resolve gallery directory or exit with a clear error."""
    try:
        return resolve_gallery_dir(gallery_dir)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc
