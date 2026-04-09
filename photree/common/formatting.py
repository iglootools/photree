"""Shared UI constants and formatting helpers.

All constants use Rich markup and must be printed via ``console.print``.
"""

from __future__ import annotations

CHECK = "[green]\u2713[/green]"
WARNING = "[dark_orange]\u2713[/dark_orange]"
CROSS = "[red]\u2717[/red]"


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

    Uses Rich markup — print with ``console.print``.
    """
    icon = CHECK if success else CROSS
    suffix = f" ({summary})" if summary else ""
    line = f"{icon} {label}{suffix}"
    return (
        "\n".join([line, *(f"    {d}" for d in details)])
        if not success and details
        else line
    )
