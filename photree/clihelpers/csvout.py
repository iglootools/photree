"""CSV output sink shared by the ``list-*`` commands."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TextIO


def csv_output(output_file: Path | None) -> AbstractContextManager[TextIO]:
    """Return a context manager yielding the CSV sink for *output_file*.

    Writes to *output_file* when given, otherwise to ``sys.stdout``. ``stdout`` is
    wrapped in ``nullcontext`` so that leaving the ``with`` block closes a real file
    but never closes the process-wide stream.
    """
    return (
        open(output_file, "w", encoding="utf-8", newline="")
        if output_file
        else nullcontext(sys.stdout)
    )
