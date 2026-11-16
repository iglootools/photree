import typer

from ...clihelpers.runtime import runtime_of
from ...clihelpers.sysdeps import require_system_deps
from ...common.sysdeps import SystemDependency
from . import check_app


@check_app.command("system")
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
