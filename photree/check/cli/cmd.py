"""CLI command for ``photree check``."""

from __future__ import annotations

from ...clihelpers.sysdeps import require_system_deps
from ...common.sysdeps import SystemDependency
from . import check_app


@check_app.command("system")
def check_system_cmd() -> None:
    """Check that all system prerequisites are met."""
    # Same probe and output as the per-command gate, minus the header and the
    # "Run 'photree check system'" hint: this command is that diagnostic.
    require_system_deps(tuple(SystemDependency), header=None, abort_message=None)
