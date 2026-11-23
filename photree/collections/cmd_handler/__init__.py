"""
Command handlers for batch collection operations.

Each module holds one handler function and its result dataclass. A handler
orchestrates domain operations, reports progress through ``on_*`` callbacks
and returns a structured result; the ``collections`` CLI renders it.

No module in this package imports ``typer``, ``rich`` or ``clihelpers``.
"""
