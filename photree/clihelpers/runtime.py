"""The ports a CLI command runs with, real by default.

A command reads the machine and the process only through its runtime: which
binaries are installed, the working directory, the home directory, the
environment, the config file, the CPU count. Tests pass a fake :class:`Runtime`
as ``CliRunner.invoke(app, args, obj=...)`` instead of patching: Typer hands it
to every command as ``ctx.obj``.
"""

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import typer
from platformdirs import site_config_dir, user_config_dir

from photree.common.sysdeps import WhichFn
from photree.config import PhotreeConfig, load_config
from photree.config.loader import ConfigDirFn


@dataclass(frozen=True)
class Runtime:
    """The ports of a command."""

    which: WhichFn = shutil.which
    """Finds an external binary (``sips``, ``exiftool``) on ``PATH``."""
    cwd: Callable[[], Path] = Path.cwd
    """The working directory: paths are shown relative to it, and searches
    (gallery, albums) start from it. It must be the process's own: relative
    paths in arguments are resolved by the OS against that. Tests change it
    with the ``chdir`` fixture rather than faking this port."""
    home: Callable[[], Path] = Path.home
    """The user's home directory (config search, default Image Capture dir)."""
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    """The process environment (``XDG_CONFIG_HOME``)."""
    user_config_dir: ConfigDirFn = user_config_dir
    """The platform user config directory of an app."""
    site_config_dir: ConfigDirFn = site_config_dir
    """The platform site config directory of an app."""
    cpu_count: Callable[[], int | None] = os.cpu_count
    """How many workers a parallel step may start."""

    def load_config(self, config_path: str | None) -> PhotreeConfig:
        """Load the config file, searched for in this runtime's environment."""
        return load_config(
            config_path,
            environ=self.environ,
            home=self.home(),
            user_dir=self.user_config_dir,
            site_dir=self.site_config_dir,
        )


def runtime_of(ctx: typer.Context) -> Runtime:
    """The runtime on *ctx* (a test's), else the real one."""
    found = ctx.find_object(Runtime)
    return found if found is not None else Runtime()
