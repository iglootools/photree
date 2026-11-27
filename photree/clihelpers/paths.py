"""
Typer callbacks for path parameters: expand ``~``, then check and resolve.

A shell expands ``~`` only at the start of a word, so ``--gallery-dir=~/g``
(zsh leaves ``~`` after ``=`` alone) or a quoted ``"~/g"`` reaches photree as
typed. Typer checks ``exists`` and applies ``resolve_path`` to the value as
typed, before any callback sees it, and would resolve that to ``<cwd>/~/g``.
A path parameter therefore passes ``exists`` and ``resolve`` to these
callbacks instead. It keeps ``file_okay``/``dir_okay`` on the Typer
declaration, which names the metavar and the shell completion from them, and
the callback reads them from there to check the expanded path again.
"""

from collections.abc import Callable
from pathlib import Path

import typer
from typer.models import TyperPath


def _kind(*, file_okay: bool, dir_okay: bool) -> str:
    """Name what the parameter expects, as Typer's own path checks word it."""
    match file_okay, dir_okay:
        case True, False:
            return "File"
        case False, True:
            return "Directory"
        case _:
            return "Path"


def check_user_path(
    value: Path,
    *,
    exists: bool = False,
    file_okay: bool = True,
    dir_okay: bool = True,
    resolve: bool = True,
) -> Path:
    """
    Return *value* with ``~`` expanded, checked, and resolved when *resolve*.

    Raises :class:`typer.BadParameter` (exit 2) when *exists* and the path is
    missing, or when it is a file and not *file_okay*, or a directory and not
    *dir_okay*.
    """
    path = value.expanduser()
    problem = next(
        (
            message
            for failed, message in (
                (exists and not path.exists(), "does not exist"),
                (not file_okay and path.is_file(), "is a file"),
                (not dir_okay and path.is_dir(), "is a directory"),
            )
            if failed
        ),
        None,
    )
    if problem is not None:
        kind = _kind(file_okay=file_okay, dir_okay=dir_okay)
        message = f"{kind} '{path}' {problem}."
        raise typer.BadParameter(message)
    else:
        return path.resolve() if resolve else path


def _check(
    value: Path,
    param: typer.CallbackParam,
    *,
    exists: bool,
    resolve: bool,
) -> Path:
    file_okay, dir_okay = (
        (param.type.file_okay, param.type.dir_okay)
        if isinstance(param.type, TyperPath)
        else (True, True)
    )
    return check_user_path(
        value,
        exists=exists,
        file_okay=file_okay,
        dir_okay=dir_okay,
        resolve=resolve,
    )


def expand_user_path(
    *,
    exists: bool = False,
    resolve: bool = True,
) -> Callable[[typer.CallbackParam, Path | None], Path | None]:
    """
    Return a callback that expands ``~`` in a path option, checks it and resolves it.

    *exists* requires the path to exist, and *resolve* makes it absolute, as
    Typer's ``exists`` and ``resolve_path`` would. The declaration's
    ``file_okay`` and ``dir_okay`` are checked on the expanded path too. A
    failed check raises :class:`typer.BadParameter`, which exits 2.
    """

    def callback(param: typer.CallbackParam, value: Path | None) -> Path | None:
        return (
            None
            if value is None
            else _check(value, param, exists=exists, resolve=resolve)
        )

    return callback


def expand_user_paths(
    *,
    exists: bool = False,
    resolve: bool = True,
) -> Callable[[typer.CallbackParam, list[Path] | None], list[Path] | None]:
    """Return the :func:`expand_user_path` callback for a repeatable option."""

    def callback(
        param: typer.CallbackParam,
        values: list[Path] | None,
    ) -> list[Path] | None:
        return (
            None
            if values is None
            else [_check(v, param, exists=exists, resolve=resolve) for v in values]
        )

    return callback
