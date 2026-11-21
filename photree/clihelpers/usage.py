"""Usage errors: the invocation itself is wrong, whatever is on disk.

Mutually exclusive options, a command given nothing to do, an option value
photree validates itself. Click and Typer report their own usage errors before
the command runs; this covers the ones only the command body can detect.

They exit 2, as Click and Typer do, so a script tells "fix the invocation"
from "the operation failed" (1): the shared rule in
https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#exit-with-0-1-or-2.
"""

import typer

from .console import err_console

USAGE_ERROR_EXIT_CODE = 2


def usage_error(message: str, *, markup: bool = True) -> typer.Exit:
    """Print *message* to stderr and return the exit to raise.

    Returned, not raised, so the call site reads ``raise usage_error(...)``
    (control flow stays visible, and ``from exc`` still chains). Pass
    ``markup=False`` when *message* embeds user text or ``[``.
    """
    err_console.print(message, markup=markup)
    return typer.Exit(code=USAGE_ERROR_EXIT_CODE)
