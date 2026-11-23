"""
The face model archive: pinned by URL and sha256, downloaded and verified.

insightface downloads its model zoo from a GitHub release tag
(``model-zoo``) that can be moved, checks no hash, and extracts whatever it
received. A replaced or tampered archive would silently change every
embedding, and the model name and version photree records would not tell.
photree therefore fetches the archive itself, checks it against the sha256
pinned here, and hands insightface a directory that already holds it.
"""

import hashlib
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelArchive:
    """A model zoo archive insightface loads, pinned by its URL and sha256."""

    name: str
    url: str
    sha256: str


BUFFALO_L = ModelArchive(
    name="buffalo_l",
    url="https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip",
    sha256="80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f",
)
"""The default model. To move to another archive, download it, review it, and
pin its ``shasum -a 256``; the hash is the only thing that says it changed."""

MODEL_ARCHIVES = {archive.name: archive for archive in (BUFFALO_L,)}
"""Every model photree can load, by name."""

VERIFIED_MARKER = ".photree-sha256"
"""File in an extracted model directory holding the sha256 it was verified as."""


class ModelChecksumError(OSError):
    """The downloaded model archive does not have the pinned sha256."""

    def __init__(self, *, url: str, expected: str, actual: str) -> None:
        """Build the error from the archive's URL and the two hashes."""
        self.url = url
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"face model archive {url} has sha256 {actual}, expected {expected}",
        )


class UnknownModelError(ValueError):
    """No archive is pinned for the requested model name."""

    def __init__(self, model_name: str) -> None:
        """Build the error from the model name."""
        self.model_name = model_name
        super().__init__(f"no pinned archive for face model {model_name!r}")


type DownloadFn = Callable[[str, Path], None]
"""Writes the content at a URL to a path: :func:`download_url`, or a test fake."""


def download_url(url: str, dst: Path) -> None:
    """Write the content at *url* to *dst*, streaming it."""
    with urllib.request.urlopen(url) as response, dst.open("wb") as f:  # noqa: S310 - the URL is a pinned https constant
        shutil.copyfileobj(response, f)


def compute_sha256(path: Path) -> str:
    """Return the hex sha256 of the file at *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_model_archive(model_name: str) -> ModelArchive:
    """Return the pinned archive of *model_name*, or raise UnknownModelError."""
    match MODEL_ARCHIVES.get(model_name):
        case None:
            raise UnknownModelError(model_name)
        case archive:
            return archive


def ensure_model(
    root: Path,
    archive: ModelArchive,
    *,
    download: DownloadFn = download_url,
) -> Path:
    """
    Make *root*'s ``models/<name>/`` hold *archive*, verified; return that dir.

    Does nothing when the directory was already extracted from an archive
    with the pinned hash. Otherwise uses the archive left in ``models/`` (by
    insightface, or an earlier run) if its hash matches, else downloads it,
    and extracts it afresh. Raises :class:`ModelChecksumError`, keeping
    nothing of the download, when the hash differs.
    """
    models_dir = root / "models"
    model_dir = models_dir / archive.name
    marker = model_dir / VERIFIED_MARKER
    if (
        marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == archive.sha256
    ):
        return model_dir
    zip_path = models_dir / f"{archive.name}.zip"
    models_dir.mkdir(parents=True, exist_ok=True)
    if not (zip_path.is_file() and compute_sha256(zip_path) == archive.sha256):
        _download_verified(archive, zip_path, download=download)
    _extract(zip_path, model_dir)
    marker.write_text(f"{archive.sha256}\n", encoding="utf-8")
    return model_dir


def _download_verified(
    archive: ModelArchive,
    zip_path: Path,
    *,
    download: DownloadFn,
) -> None:
    partial = zip_path.with_name(f"{zip_path.name}.part")
    try:
        download(archive.url, partial)
        actual = compute_sha256(partial)
        if actual != archive.sha256:
            raise ModelChecksumError(
                url=archive.url,
                expected=archive.sha256,
                actual=actual,
            )
        partial.replace(zip_path)
    finally:
        partial.unlink(missing_ok=True)


def _extract(zip_path: Path, model_dir: Path) -> None:
    """Extract *zip_path* into *model_dir*, replacing what was there."""
    staging = model_dir.with_name(f"{model_dir.name}.partial")
    shutil.rmtree(staging, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(staging)
    shutil.rmtree(model_dir, ignore_errors=True)
    staging.replace(model_dir)
