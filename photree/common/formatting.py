"""Shared UI constants and formatting helpers.

All constants use Rich markup and must be printed via ``console.print``.
"""

from __future__ import annotations

import textwrap

from rich.markup import escape

INDENT = "  "
CHECK = "[green]\u2713[/green]"
WARNING = "[dark_orange]\u2713[/dark_orange]"
CROSS = "[red]\u2717[/red]"
# Distinct warning sign (\u26a0) for outcomes that are neither success nor failure,
# e.g. an album skipped because a to-import-* dir has nothing to import.
WARN_SIGN = "[dark_orange]\u26a0[/dark_orange]"


def markup_escape(value: object) -> str:
    """Escape *value* for interpolation into a Rich markup string.

    Rich parses ``[...]`` as markup tags and silently drops the ones it does
    not recognize, so an album named ``2024-07-14 - Hiking [private]`` would
    print without its tag. Every piece of user-derived text (names, paths,
    filenames, reasons, exception messages) interpolated next to intentional
    markup such as ``CHECK``/``CROSS`` must go through this helper; text with
    no intentional markup can instead be printed with ``markup=False``.
    """
    return escape(str(value))


def indent(text: str, level: int = 1) -> str:
    """Prefix every non-empty line of *text* with *level* indentation units.

    Formatting helpers return unindented lines; the call site decides how deep
    they nest, so the same helper renders correctly at any level.
    """
    return textwrap.indent(text, INDENT * level)


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
    """Format a check result as a single line with optional details.

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
