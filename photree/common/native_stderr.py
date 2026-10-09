"""Filter what native (C/C++) code writes to stderr.

Native libraries write straight to file descriptor 2, bypassing ``sys.stderr``,
so ``contextlib.redirect_stderr`` cannot touch their output. This captures the
descriptor itself, then re-emits every line except the ones a predicate marks
as known noise — nothing else is lost, so real errors still surface.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from collections.abc import Callable, Generator


@contextlib.contextmanager
def filter_native_stderr(
    is_noise: Callable[[str], bool],
) -> Generator[None, None, None]:
    """Capture fd 2 for the duration of the block, then re-emit non-noise lines."""
    sys.stderr.flush()
    saved_fd = os.dup(2)
    with tempfile.TemporaryFile() as captured:
        os.dup2(captured.fileno(), 2)
        try:
            yield
        finally:
            sys.stderr.flush()
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
            captured.seek(0)
            lines = captured.read().decode(errors="replace").splitlines(keepends=True)
            sys.stderr.write("".join(line for line in lines if not is_noise(line)))
            sys.stderr.flush()
