"""Typer CLI for photree."""

import sys
from pathlib import Path

from ..album.cli.helpers import format_config_error, format_media_source_conflict
from ..album.store.media_sources_discovery import MediaSourceConflictError
from ..clihelpers.console import err_console
from ..clihelpers.resolution import format_invalid_metadata
from ..clihelpers.sysdeps import format_missing_troubleshoot
from ..common.sysdeps import MissingSystemDependencyError
from ..config import ConfigError
from ..foundation.metadata_io import InvalidMetadataError
from .app import app

__all__ = ["app", "main"]


def main() -> None:
    """Main CLI entry point."""
    try:
        app()
    except MissingSystemDependencyError as exc:
        # Safety net for code paths not fronted by require_system_deps: without
        # it a missing binary surfaces as an unhandled traceback.
        err_console.print(str(exc), markup=False)
        err_console.print("")
        err_console.print(format_missing_troubleshoot(exc.missing))
        sys.exit(1)
    except InvalidMetadataError as exc:
        # Safety net for any store read not handled closer to the command: a
        # corrupt metadata file must stop the run legibly, never be treated as
        # absent (which would mint new IDs) nor surface as a traceback.
        err_console.print(format_invalid_metadata(exc, Path.cwd()), markup=False)
        sys.exit(1)
    except MediaSourceConflictError as exc:
        # Safety net for media source discovery not wrapped by the command: an
        # iOS/std name clash is a user-fixable album problem, not a traceback.
        err_console.print(format_media_source_conflict(exc, Path.cwd()), markup=False)
        sys.exit(1)
    except ConfigError as exc:
        # Safety net for config reads not handled by the command: an invalid
        # config file is a configuration error (exit 2), not a traceback.
        err_console.print(format_config_error(exc), markup=False)
        sys.exit(2)
