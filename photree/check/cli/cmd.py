"""The ``photree check system`` command."""

import typer

from photree.check.cli.app import app
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import require_system_deps
from photree.common.sysdeps import SystemDependency


@app.command("system")
def check_system_cmd(ctx: typer.Context) -> None:
    """Check that all system prerequisites are met."""
    # Same probe and output as the per-command gate, minus the header and the
    # "Run 'photree check system'" hint: this command is that diagnostic.
    require_system_deps(
        tuple(SystemDependency),
        header=None,
        abort_message=None,
        which=runtime_of(ctx).which,
    )
