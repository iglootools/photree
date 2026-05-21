"""Command handlers for gallery operations.

Each module contains a single handler function + its result dataclass.
These functions orchestrate domain operations, accept ``on_*`` callbacks
for progress notification, and return structured results.

No module in this package imports ``typer``, ``rich``, or ``clihelpers``.
"""
