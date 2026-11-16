"""Fakes injected in place of real dependencies (docs/guidelines.md, Tests)."""

from dataclasses import replace
from pathlib import Path

from photree.album.cli.runtime import AlbumRuntime, RunImportFn, widen
from photree.clihelpers.runtime import Runtime
from photree.common.sysdeps import SystemDependency, WhichFn

FAKE_HOME = Path("/nonexistent/photree-test-home")
"""A home directory that does not exist: no config file, no Image Capture dir."""


def fake_which(*present: SystemDependency) -> WhichFn:
    """A ``which`` that finds *present* and nothing else."""
    names = {str(dependency) for dependency in present}
    return lambda name: f"/usr/bin/{name}" if name in names else None


def fake_runtime(*present: SystemDependency, cpu_count: int = 2) -> Runtime:
    """A CLI runtime on which only *present* are installed.

    Nothing of the developer's machine leaks in: the home directory does not
    exist, the environment is empty, and the platform config directories
    hold nothing, so only a ``--config`` the test passes is read. The working
    directory stays the process's (see :attr:`Runtime.cwd`).

    Pass it as ``CliRunner().invoke(app, args, obj=fake_runtime(...))``. A
    command that gets past the gate and then shells out still runs the real
    binary, or fails with ``FileNotFoundError`` where it is missing; either
    way, the fake media files of a test fail to convert.
    """
    return Runtime(
        which=fake_which(*present),
        home=lambda: FAKE_HOME,
        environ={},
        user_config_dir=lambda app: str(FAKE_HOME / "user-config" / app),
        site_config_dir=lambda app: str(FAKE_HOME / "site-config" / app),
        cpu_count=lambda: cpu_count,
    )


def fake_album_runtime(
    *present: SystemDependency, run_import: RunImportFn
) -> AlbumRuntime:
    """:func:`fake_runtime` with a fake album import in place of the real one."""
    return replace(widen(fake_runtime(*present)), run_import=run_import)


ALL_DEPS_RUNTIME = fake_runtime(*SystemDependency)
"""Every system dependency installed: the gate passes."""

ALL_DEPS_WHICH = fake_which(*SystemDependency)
"""A ``which`` that finds every system dependency."""
