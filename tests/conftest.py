"""Shared test fixtures."""

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NoReturn

import pytest


@pytest.fixture
def monkeypatch() -> NoReturn:
    """Replace pytest's fixture for every test: tests do not patch.

    Inject a fake through a parameter instead (docs/guidelines.md, Tests).
    The documented exceptions use ``pytest.MonkeyPatch``, which ruff bans
    everywhere else (TID251), through a fixture of their own in the test
    module.
    """
    pytest.fail(
        "The monkeypatch fixture is disabled: inject a fake through a parameter"
        " instead (docs/guidelines.md, Tests).",
        pytrace=False,
    )


@pytest.fixture
def chdir() -> Iterator[Callable[[Path], None]]:
    """Change the working directory until the end of the test.

    Stands in for ``monkeypatch.chdir``, which went with the fixture above.
    """
    with contextlib.ExitStack() as stack:
        yield lambda path: stack.enter_context(contextlib.chdir(path))
