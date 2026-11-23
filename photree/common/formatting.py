"""
Shared UI constants and formatting helpers.

All constants use Rich markup and must be printed via ``console.print``.
"""

import re
import textwrap
from collections.abc import Iterable

INDENT = "  "
CHECK = "[green]\u2713[/green]"
WARNING = "[dark_orange]\u2713[/dark_orange]"
CROSS = "[red]\u2717[/red]"
# Distinct warning sign (\u26a0) for outcomes that are neither success nor failure,
# e.g. an album skipped because a to-import-* dir has nothing to import.
WARN_SIGN = "[dark_orange]\u26a0[/dark_orange]"
# Plain text, unlike the constants above: Rich would parse it as a style tag,
# so print it through ``format_dry_run``.
DRY_RUN_LABEL = "[dry-run]"

# What Rich parses as a tag (``[bold]``, ``[/]``, ``[#fff]``, ``[@click]``) and
# the backslashes in front of it, as in ``rich.markup.escape``. This module
# builds markup for the domain output layers, which may not import Rich, so
# the escaping is reproduced here; a unit test keeps it equal to Rich's.
_MARKUP_TAG = re.compile(r"(\\*)(\[[a-z#/@][^[]*?])")


def markup_escape(value: object) -> str:
    """
    Escape *value* for interpolation into a Rich markup string.

    Rich parses ``[...]`` as markup tags and silently drops the ones it does
    not recognize, so an album named ``2024-07-14 - Hiking [private]`` would
    print without its tag. Every piece of user-derived text (names, paths,
    filenames, reasons, exception messages) interpolated next to intentional
    markup such as ``CHECK``/``CROSS`` must go through this helper; text with
    no intentional markup can instead be printed with ``markup=False``.

    Behaves as ``rich.markup.escape``: each backslash before a tag is doubled
    and the tag gets one more, and a lone trailing backslash is doubled so it
    cannot escape markup that follows.
    """
    escaped = _MARKUP_TAG.sub(
        lambda match: f"{match[1]}{match[1]}\\{match[2]}",
        str(value),
    )
    return (
        f"{escaped}\\"
        if escaped.endswith("\\") and not escaped.endswith("\\\\")
        else escaped
    )


def indent(text: str, level: int = 1) -> str:
    """
    Prefix every non-empty line of *text* with *level* indentation units.

    Formatting helpers return unindented lines; the call site decides how deep
    they nest, so the same helper renders correctly at any level.
    """
    return textwrap.indent(text, INDENT * level)


def format_dry_run(text: str, *, dry_run: bool, markup: bool = False) -> str:
    """
    Start *text* with ``DRY_RUN_LABEL`` when *dry_run*, after any leading newlines.

    A line describing an action takes the label; a block (a summary, a
    section, a batch tally) takes it once, on its header or summary line.
    Pass ``markup=True`` when *text* is Rich markup printed with
    ``console.print``: the label is then escaped, so Rich does not swallow it
    as an unknown tag.
    """
    body = text.lstrip("\n")
    label = markup_escape(DRY_RUN_LABEL) if markup else DRY_RUN_LABEL
    return f"{text[: len(text) - len(body)]}{label} {body}" if dry_run else text


def format_flags(flags: Iterable[tuple[str, bool]]) -> str:
    """
    Return the command-line flags that are set, each after a space.

    *flags* pairs each flag (``"--dry-run"``) with whether the run used it,
    so a suggested follow-up command repeats the options of the run that
    printed it. Returns ``""`` when none is set.
    """
    return "".join(f" {flag}" for flag, enabled in flags if enabled)


def rich_warning_text(text: str) -> str:
    """Wrap *text* in Rich warning markup (dark orange)."""
    return f"[dark_orange]{text}[/dark_orange]"


def format_check_line(
    label: str,
    *,
    success: bool,
    summary: str = "",
    details: tuple[str, ...] = (),
) -> str:
    """
    Format a check result as a single line with optional details.

    Success: ``✓ label (summary)``
    Failure: ``✗ label (summary)`` followed by indented details.

    *label*, *summary* and *details* are plain text, escaped here. The result
    uses Rich markup — print with ``console.print``.
    """
    icon = CHECK if success else CROSS
    suffix = f" ({markup_escape(summary)})" if summary else ""
    line = f"{icon} {markup_escape(label)}{suffix}"
    return (
        "\n".join([line, *(indent(markup_escape(d), 2) for d in details)])
        if not success and details
        else line
    )
