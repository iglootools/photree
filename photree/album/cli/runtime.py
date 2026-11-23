"""
The album-level ports of a CLI command, on top of the shared runtime.

:class:`~photree.clihelpers.runtime.Runtime` sits below ``album`` in the
layering, so it cannot name album operations. :class:`AlbumRuntime` adds
them, real by default; a test passes one, with fakes, as ``obj``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, fields

import typer

from photree.album.faces.detect import (
    FaceAnalyzerFactory,
    MakeThumbnailFn,
    generate_thumbnail,
    memoized_face_analyzer_factory,
)
from photree.album.importer import album_import
from photree.album.importer.album_import import AlbumImportResult
from photree.clihelpers.runtime import Runtime

type RunImportFn = Callable[..., AlbumImportResult]


@dataclass(frozen=True)
class AlbumRuntime(Runtime):
    """The shared ports, plus the album operations a command runs."""

    run_import: RunImportFn = album_import.run_import
    """Imports an album's staging entries (``album import``)."""
    face_analyzer_factory: FaceAnalyzerFactory = field(
        default_factory=memoized_face_analyzer_factory,
    )
    """Builds the face analyzer on first use, once per run (``detect-faces``)."""
    make_face_thumbnail: MakeThumbnailFn = generate_thumbnail
    """Writes the thumbnail face detection reads (``detect-faces``)."""


def widen(base: Runtime) -> AlbumRuntime:
    """*base*'s ports, with the real album operations."""
    return (
        base
        if isinstance(base, AlbumRuntime)
        else AlbumRuntime(**{f.name: getattr(base, f.name) for f in fields(Runtime)})
    )


def album_runtime_of(ctx: typer.Context) -> AlbumRuntime:
    """
    Return the album runtime on *ctx*, else the real one.

    The runtime on *ctx* (a test's, or the one ``main`` passes) is widened
    with the real album operations unless it already carries some.
    """
    found = ctx.find_object(Runtime)
    return widen(found) if found is not None else AlbumRuntime()
