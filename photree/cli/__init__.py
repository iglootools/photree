"""The ``photree`` console entry point and its root command group."""

import sys
from collections.abc import Callable

from photree.album.cli.face_model_error import (
    format_model_checksum_error,
    format_model_download_error,
)
from photree.album.cli.media_source_conflict import format_media_source_conflict
from photree.album.faces.model import ModelChecksumError, ModelDownloadError
from photree.album.store.media_sources_discovery import MediaSourceConflictError
from photree.cli.app import app
from photree.clihelpers.config_errors import format_config_error
from photree.clihelpers.console import err_console
from photree.clihelpers.resolution import format_invalid_metadata
from photree.clihelpers.runtime import Runtime
from photree.common.fs import FileDeletionError
from photree.common.fs_output import format_file_deletion_error
from photree.common.sysdeps import MissingSystemDependencyError
from photree.common.sysdeps_output import format_missing_troubleshoot
from photree.config import ConfigError
from photree.foundation.metadata_io import InvalidMetadataError

__all__ = ["app", "main"]


def main(*, run: Callable[..., object] = app, runtime: Runtime | None = None) -> None:
    """
    Run the console entry point.

    Runs *run* (the app) with *runtime* (the real one by default) as every
    command's ``ctx.obj``, turning the domain errors no command handled into a
    message and an exit code instead of a traceback.
    """
    resolved = runtime if runtime is not None else Runtime()
    try:
        run(obj=resolved)
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
        err_console.print(format_invalid_metadata(exc, resolved.cwd()), markup=False)
        sys.exit(1)
    except MediaSourceConflictError as exc:
        # Safety net for media source discovery not wrapped by the command: an
        # iOS/std name clash is a user-fixable album problem, not a traceback.
        err_console.print(
            format_media_source_conflict(exc, resolved.cwd()),
            markup=False,
        )
        sys.exit(1)
    except ModelChecksumError as exc:
        # Raised where the face model first loads, deep in a refresh or an
        # import: whichever command got there, the run cannot detect faces.
        err_console.print(format_model_checksum_error(exc), markup=False)
        sys.exit(1)
    except ModelDownloadError as exc:
        # Raised where the face model first loads, as the checksum error is.
        err_console.print(format_model_download_error(exc), markup=False)
        sys.exit(1)
    except FileDeletionError as exc:
        # A destructive command (fix, rm-media) stopped partway: say which
        # files are already gone, since the run cannot be retried as if
        # nothing happened.
        err_console.print(format_file_deletion_error(exc, resolved.cwd()), markup=False)
        sys.exit(1)
    except ConfigError as exc:
        # Safety net for config reads not handled by the command: an invalid
        # config file is a configuration error (exit 2), not a traceback.
        err_console.print(format_config_error(exc), markup=False)
        sys.exit(2)
