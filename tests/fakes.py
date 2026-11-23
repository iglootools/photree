"""Fakes injected in place of real dependencies (docs/guidelines.md, Tests)."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from photree.album.cli.runtime import AlbumRuntime, RunImportFn, widen
from photree.clihelpers.runtime import Runtime
from photree.common.sysdeps import SystemDependency, WhichFn

FAKE_HOME = Path("/nonexistent/photree-test-home")
"""A home directory that does not exist: no config file, no Image Capture dir."""


def fake_which(*present: SystemDependency) -> WhichFn:
    """Return a ``which`` that finds *present* and nothing else."""
    names = {str(dependency) for dependency in present}
    return lambda name: f"/usr/bin/{name}" if name in names else None


def fake_runtime(*present: SystemDependency, cpu_count: int = 2) -> Runtime:
    """
    Return a CLI runtime on which only *present* are installed.

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
    *present: SystemDependency,
    run_import: RunImportFn,
) -> AlbumRuntime:
    """:func:`fake_runtime` with a fake album import in place of the real one."""
    return replace(widen(fake_runtime(*present)), run_import=run_import)


ALL_DEPS_RUNTIME = fake_runtime(*SystemDependency)
"""Every system dependency installed: the gate passes."""

ALL_DEPS_WHICH = fake_which(*SystemDependency)
"""A ``which`` that finds every system dependency."""


class FakeExifTool:
    """
    Stands in for a running ``ExifToolHelper``: a fixed timestamp per file name.

    *timestamps* maps a file's name (not its path) to an exiftool-formatted
    ``DateTimeOriginal`` (``2024:07:14 10:00:00``); files it does not name
    have no date tag.
    """

    def __init__(self, timestamps: Mapping[str, str]) -> None:
        """Build the fake from the timestamp of each file name."""
        self.timestamps = dict(timestamps)

    def get_tags(self, files: list[str], tags: list[str]) -> list[dict[str, object]]:  # noqa: ARG002 - ExifTagReader's signature
        """Return each file's ``EXIF:DateTimeOriginal``, or no tag at all."""
        return [
            {
                "SourceFile": f,
                **(
                    {"EXIF:DateTimeOriginal": self.timestamps[Path(f).name]}
                    if Path(f).name in self.timestamps
                    else {}
                ),
            }
            for f in files
        ]
