"""Shared UI constants for check marks and crosses.

All constants use Rich markup and must be printed via ``console.print``.
"""

CHECK = "[green]\u2713[/green]"
WARNING = "[dark_orange]\u2713[/dark_orange]"
CROSS = "[red]\u2717[/red]"


def rich_warning_text(text: str) -> str:
    """Wrap *text* in Rich warning markup (dark orange)."""
    return f"[dark_orange]{text}[/dark_orange]"
