"""Shared test fixtures."""

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


@pytest.fixture
def chdir() -> Iterator[Callable[[Path], None]]:
    """Change the working directory until the end of the test."""
    with contextlib.ExitStack() as stack:
        yield lambda path: stack.enter_context(contextlib.chdir(path))
