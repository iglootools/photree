"""Shared UI constants for check marks and crosses.

Three representations for three rendering contexts:

- ``CHECK`` / ``CROSS`` — ANSI-escaped strings for use with ``typer.echo``
- ``RICH_CHECK`` / ``RICH_CROSS`` — Rich markup for use with ``console.print``
"""

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"

CHECK = f"{GREEN}\u2713{RESET}"
CROSS = f"{RED}\u2717{RESET}"

RICH_CHECK = "[green]\u2713[/green]"
RICH_CROSS = "[red]\u2717[/red]"
