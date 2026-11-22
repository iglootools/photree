"""
Usage errors: the invocation itself is wrong, whatever is on disk.

Mutually exclusive options, a command given nothing to do, an option value
photree validates itself. Click and Typer report their own usage errors before
the command runs; this covers the ones only the command body can detect.

They exit 2, as Click and Typer do, so a script tells "fix the invocation"
from "the operation failed" (1): the shared rule in
https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#exit-with-0-1-or-2.
"""

from collections.abc import Sequence

import typer

from photree.clihelpers.console import err_console

USAGE_ERROR_EXIT_CODE = 2


def usage_error(message: str, *, markup: bool = True) -> typer.Exit:
    """
    Print *message* to stderr and return the exit to raise.

    Returned, not raised, so the call site reads ``raise usage_error(...)``
    (control flow stays visible, and ``from exc`` still chains). Pass
    ``markup=False`` when *message* embeds user text or ``[``.
    """
    err_console.print(message, markup=markup)
    return typer.Exit(code=USAGE_ERROR_EXIT_CODE)


def _join_options(options: Sequence[str], conjunction: str) -> str:
    match options:
        case [only]:
            return only
        case [first, second]:
            return f"{first} {conjunction} {second}"
        case [*rest, last]:
            return f"{', '.join(rest)}, {conjunction} {last}"
        case _:
            return ""


def _help_hint(command: str | None, purpose: str) -> str:
    return f"\nRun 'photree {command} --help' {purpose}." if command else ""


def mutually_exclusive_error(
    options: Sequence[str],
    *,
    advice: str | None = None,
    command: str | None = None,
) -> typer.Exit:
    """
    Print that *options* cannot be combined, and return the exit to raise.

    *advice*, when given, says how to choose between them; *command*
    (``albums import``) adds a pointer to its help.
    """
    reason = f": {advice}." if advice else "."
    return usage_error(
        f"{_join_options(options, 'and')} are mutually exclusive{reason}"
        + _help_hint(command, "for usage"),
        markup=False,
    )


def exactly_one_error(options: Sequence[str]) -> typer.Exit:
    """Print that exactly one of *options* is required, and return the exit to raise."""
    return usage_error(
        f"Specify exactly one of {_join_options(options, 'or')}.",
        markup=False,
    )


def no_fields_error(options: Sequence[str]) -> typer.Exit:
    """Print that no field *options* was given, and return the exit to raise."""
    return usage_error(
        f"No fields specified. Use {_join_options(options, 'or')} to set a value.",
        markup=False,
    )


def no_files_error() -> typer.Exit:
    """Print that the command was given no files, and return the exit to raise."""
    return usage_error("No files specified.", markup=False)


def invalid_fix_error(error: Exception, *, command: str) -> typer.Exit:
    """
    Print why the fix options of *command* are invalid, and return the exit to raise.

    *error* is the domain's validation error; its text says what is wrong, and
    the hint points to *command*'s help for the available fixes.
    """
    return usage_error(
        f"{error}" + _help_hint(command, "for the available fixes"),
        markup=False,
    )


def invalid_value_error(
    *,
    name: str,
    value: object,
    expected: str,
    command: str | None = None,
) -> typer.Exit:
    """
    Print that *value* is not a valid *name*, and return the exit to raise.

    *expected* describes a valid value; *command* adds a pointer to its help.
    """
    return usage_error(
        f'Invalid {name} "{value}", expected {expected}.'
        + _help_hint(command, "for details"),
        markup=False,
    )
