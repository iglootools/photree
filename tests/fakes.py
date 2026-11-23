"""Fakes injected in place of real dependencies (docs/guidelines.md, Tests)."""

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from typer.testing import CliRunner, Result  # noqa: TID251 - wrapped by invoke_cli

from photree.album.cli.runtime import AlbumRuntime, RunImportFn, widen
from photree.album.faces.detect import MakeThumbnailFn, ThumbnailResult
from photree.album.faces.protocol import EMBEDDING_DIM
from photree.album.importer import album_import
from photree.album.jpeg import jpeg_name
from photree.album.refresh import RefreshFn, refresh_album_derived_data
from photree.cli import app
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

    Pass it as ``invoke_cli(args, runtime=fake_runtime(...))``. A command
    that gets past the gate and then shells out still runs the real binary,
    or fails with ``FileNotFoundError`` where it is missing; either way, the
    fake media files of a test fail to convert.
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
    run_import: RunImportFn = album_import.run_import,
    refresh: RefreshFn = refresh_album_derived_data,
) -> AlbumRuntime:
    """:func:`fake_runtime` with fakes in place of the album operations given."""
    return replace(
        widen(fake_runtime(*present)),
        run_import=run_import,
        refresh=refresh,
    )


@dataclass(frozen=True)
class FakeFace:
    """An insightface ``Face`` with what photree reads, and no optional models."""

    det_score: float
    bbox: np.ndarray
    kps: np.ndarray
    embedding: np.ndarray


class FakeFaceDetector:
    """Stands in for a prepared ``FaceAnalysis``: one face in every image."""

    def get(self, img: np.ndarray) -> list[Any]:  # noqa: ARG002 - FaceDetector's signature
        """Return one face, whatever the image."""
        return [
            FakeFace(
                det_score=0.9,
                bbox=np.array([1, 2, 30, 40], dtype=np.float32),
                kps=np.zeros((5, 2), dtype=np.float32),
                embedding=np.ones(EMBEDDING_DIM, dtype=np.float32),
            ),
        ]


FAKE_THUMBNAIL_SIZE = (64, 48)
"""The ``(width, height)`` of a thumbnail :func:`fake_make_thumbnail` writes."""

FAKE_ORIGINAL_SIZE = (4032, 3024)
"""The ``(width, height)`` :func:`fake_make_thumbnail` reports for an original."""


def fake_make_thumbnail(*, broken: frozenset[str] = frozenset()) -> MakeThumbnailFn:
    """
    Return a thumbnailer that needs no ``sips``: a black JPEG for every key.

    Keys in *broken* get a file that is not an image, which detection then
    reports as failed.
    """

    def make(key: str, file_name: str, src: Path, dst: Path) -> ThumbnailResult:  # noqa: ARG001 - MakeThumbnailFn's signature
        dst.parent.mkdir(parents=True, exist_ok=True)
        width, height = FAKE_THUMBNAIL_SIZE
        if key in broken:
            dst.write_bytes(b"not a jpeg")
        else:
            cv2.imwrite(str(dst), np.zeros((height, width, 3), dtype=np.uint8))
        orig_width, orig_height = FAKE_ORIGINAL_SIZE
        return ThumbnailResult(
            key=key,
            file_name=file_name,
            thumb_path=dst,
            orig_width=orig_width,
            orig_height=orig_height,
        )

    return make


def fake_face_runtime(*, broken: frozenset[str] = frozenset()) -> AlbumRuntime:
    """
    Return an album runtime with every dependency and fake face detection.

    Detection finds one face per image, on thumbnails written without ``sips``
    (:func:`fake_make_thumbnail`, *broken* passed on).
    """
    return replace(
        widen(fake_runtime(*SystemDependency)),
        face_analyzer_factory=FakeFaceDetector,
        make_face_thumbnail=fake_make_thumbnail(broken=broken),
    )


ALL_DEPS_RUNTIME = fake_runtime(*SystemDependency)
"""Every system dependency installed: the gate passes."""

ALL_DEPS_WHICH = fake_which(*SystemDependency)
"""A ``which`` that finds every system dependency."""


def invoke_cli(args: Sequence[str], *, runtime: Runtime = ALL_DEPS_RUNTIME) -> Result:
    """
    Run ``photree`` with *args* on *runtime*, every dependency installed by default.

    The only way tests run the CLI: invoked without a runtime, a command falls
    back to the real one and reads the developer's ``PATH``, home directory
    and config file. ``typer.testing.CliRunner`` is banned elsewhere (ruff
    TID251) so that no test can skip it.
    """
    return CliRunner().invoke(app, args, obj=runtime)


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


def noop_convert(_src: Path, _dst_dir: Path, *, dry_run: bool) -> Path | None:  # noqa: ARG001 - ConvertFile's signature
    """Convert nothing: a ``ConvertFile`` that keeps ``sips`` off fake HEIC files."""
    return None


def copy_convert_single(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """
    Copy each file as-is under its JPEG name, as a ``ConvertFile`` without ``sips``.

    For tests on platforms without ``sips``: HEIC and DNG files are copied
    unconverted, so the output is not true JPEG.
    """
    target = jpeg_name(src.name)
    if target is None:
        return None
    dst = dst_dir / target
    if not dry_run:
        shutil.copy(src, dst)
    return dst
