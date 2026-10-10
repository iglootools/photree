"""rm-upstream fix operation.

Deleting a file from a browsable directory (``{name}-img/``, ``{name}-jpg/``,
``{name}-vid/``) is how a user curates an album; ``rm-upstream`` propagates
those deletions back to the archive.

Because the browsable directories are the *only* signal, a directory that was
never generated (e.g. ``{name}-jpg/`` after ``--skip-heic-to-jpeg``) looks
exactly like one whose every file was deleted. Taking that at face value used
to wipe the whole archive. So:

- a missing signal directory is never used as a signal (reported as skipped);
- ``{name}-jpg/`` is derived, and an empty one is just as ambiguous (it is
  created empty when conversion is skipped): when it holds none of the JPEGs
  it should, it is skipped too, unless ``force`` is set;
- a plan that would delete every item of an archive — e.g. after emptying
  ``{name}-img/`` or ``{name}-vid/`` — is refused unless ``force`` is set.

Every source is planned before anything is deleted, so a refusal leaves the
album untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...common.fs import delete_files, list_files
from .. import browsable as browsable_module
from ..formats import IMG_EXTENSIONS
from ..jpeg import jpeg_name
from ..store.file_matching import find_files_by_key
from ..store.media_source import MediaSource
from .helpers import _require_archive

# ---------------------------------------------------------------------------
# Results and errors
# ---------------------------------------------------------------------------


class MediaKind(StrEnum):
    IMAGES = "images"
    VIDEOS = "videos"


class SignalSkipReason(StrEnum):
    """Why a browsable directory was not used as a deletion signal."""

    MISSING = "missing"  # the directory does not exist
    NO_EXPECTED_FILES = "no-expected-files"  # exists, but holds none it should


@dataclass(frozen=True)
class RmUpstreamSkip:
    """A browsable directory ignored as a deletion signal, and why."""

    media_source: str
    directory: str  # album-relative, e.g. "main-jpg"
    reason: SignalSkipReason


class RmUpstreamRefusedError(ValueError):
    """Propagating deletions would remove every item of an archive.

    Raised before anything is deleted. Pass ``force`` (``--force``) to proceed.
    """

    def __init__(self, media_source: str, kind: MediaKind, key_count: int) -> None:
        self.media_source = media_source
        self.kind = kind
        self.key_count = key_count
        super().__init__(
            f"rm-upstream would delete all {key_count} {kind} of media source "
            f"{media_source!r}; refusing without --force"
        )


@dataclass(frozen=True)
class RmUpstreamHeicResult:
    """Result of propagating image deletions."""

    removed_jpeg: tuple[str, ...]
    removed_browsable: tuple[str, ...]
    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamMovResult:
    """Result of propagating video deletions."""

    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamResult:
    """Result of propagating deletions from browsable dirs to archive dirs."""

    heic: RmUpstreamHeicResult
    mov: RmUpstreamMovResult
    skipped: tuple[RmUpstreamSkip, ...] = ()


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Signal:
    """Keys a browsable directory says were deleted, or why it was ignored."""

    keys: frozenset[str] = frozenset()
    skip: RmUpstreamSkip | None = None


@dataclass(frozen=True)
class RmUpstreamPlan:
    """Keys to delete for one media source, computed without touching disk."""

    ms: MediaSource
    image_keys: frozenset[str]
    video_keys: frozenset[str]
    archive_image_keys: frozenset[str]
    archive_video_keys: frozenset[str]
    skipped: tuple[RmUpstreamSkip, ...]

    def refusal(self) -> RmUpstreamRefusedError | None:
        """The error to raise if this plan would empty an archive, else None."""
        wipes = [
            (kind, archive)
            for kind, keys, archive in (
                (MediaKind.IMAGES, self.image_keys, self.archive_image_keys),
                (MediaKind.VIDEOS, self.video_keys, self.archive_video_keys),
            )
            if archive and archive <= keys
        ]
        return (
            RmUpstreamRefusedError(self.ms.name, wipes[0][0], len(wipes[0][1]))
            if wipes
            else None
        )


def _signal_skip(
    ms: MediaSource,
    directory: Path,
    subdir: str,
    *,
    expected: frozenset[str],
    present: frozenset[str],
    require_expected: bool,
    force: bool,
) -> RmUpstreamSkip | None:
    """Return why *directory* cannot be trusted as a deletion signal, if so.

    With *require_expected* (derived dirs), a directory holding none of its
    *expected* entries is not trusted either, unless *force*.
    """
    if not directory.is_dir():
        return RmUpstreamSkip(ms.name, subdir, SignalSkipReason.MISSING)
    elif require_expected and expected and not (expected & present) and not force:
        return RmUpstreamSkip(ms.name, subdir, SignalSkipReason.NO_EXPECTED_FILES)
    else:
        return None


def _deleted_keys(
    ms: MediaSource,
    directory: Path,
    subdir: str,
    *,
    expected: dict[str, str],
    present: frozenset[str],
    force: bool,
    require_expected: bool = False,
) -> _Signal:
    """Keys of *expected* (``{name: key}``) whose name is absent from *present*.

    *present* is in the same unit as *expected*'s names (filenames or keys).
    """
    skip = _signal_skip(
        ms,
        directory,
        subdir,
        expected=frozenset(expected),
        present=present,
        require_expected=require_expected,
        force=force,
    )
    return (
        _Signal(skip=skip)
        if skip is not None
        else _Signal(
            keys=frozenset(k for name, k in expected.items() if name not in present)
        )
    )


def _plan_images(
    album_dir: Path, ms: MediaSource, *, force: bool
) -> tuple[_Signal, _Signal]:
    """Signals from ``{name}-img/`` (vs. the archive) and ``{name}-jpg/`` (vs. img)."""
    key_fn = ms.key_fn
    img_files = frozenset(list_files(album_dir / ms.img_dir))
    expected_browsable = {
        filename: key_fn(filename)
        for filename, _ in browsable_module.compute_browsable_files(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            IMG_EXTENSIONS,
            key_fn,
        )
    }
    expected_jpegs = {
        name: key_fn(f) for f in img_files if (name := jpeg_name(f)) is not None
    }
    return (
        _deleted_keys(
            ms,
            album_dir / ms.img_dir,
            ms.img_dir,
            expected=expected_browsable,
            present=img_files,
            force=force,
        ),
        _deleted_keys(
            ms,
            album_dir / ms.jpg_dir,
            ms.jpg_dir,
            expected=expected_jpegs,
            present=frozenset(list_files(album_dir / ms.jpg_dir)),
            force=force,
            require_expected=True,
        ),
    )


def _plan_videos(album_dir: Path, ms: MediaSource, *, force: bool) -> _Signal:
    """Signal from ``{name}-vid/``, compared by key with ``orig-vid/``.

    Key-based (not by exact filename) so that edited videos (e.g.
    ``IMG_E0001.MOV``) are matched to their originals (``IMG_0001.MOV``).
    """
    key_fn = ms.key_fn
    orig_keys = {key_fn(f): key_fn(f) for f in list_files(album_dir / ms.orig_vid_dir)}
    return _deleted_keys(
        ms,
        album_dir / ms.vid_dir,
        ms.vid_dir,
        expected=orig_keys,
        present=frozenset(key_fn(f) for f in list_files(album_dir / ms.vid_dir)),
        force=force,
    )


def plan_rm_upstream(
    album_dir: Path, ms: MediaSource, *, force: bool = False
) -> RmUpstreamPlan:
    """Compute what :func:`rm_upstream` would delete for one media source."""
    _require_archive(album_dir, ms)
    from_img, from_jpg = _plan_images(album_dir, ms, force=force)
    from_vid = _plan_videos(album_dir, ms, force=force)
    signals = (from_img, from_jpg, from_vid)
    return RmUpstreamPlan(
        ms=ms,
        image_keys=from_img.keys | from_jpg.keys,
        video_keys=from_vid.keys,
        archive_image_keys=frozenset(
            ms.key_fn(f) for f in list_files(album_dir / ms.orig_img_dir)
        ),
        archive_video_keys=frozenset(
            ms.key_fn(f) for f in list_files(album_dir / ms.orig_vid_dir)
        ),
        skipped=tuple(sig.skip for sig in signals if sig.skip is not None),
    )


def check_rm_upstream_plans(plans: list[RmUpstreamPlan], *, force: bool) -> None:
    """Raise the first :class:`RmUpstreamRefusedError` among *plans*, unless *force*."""
    refusal = next((err for plan in plans if (err := plan.refusal()) is not None), None)
    if refusal is not None and not force:
        raise refusal


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _delete_keys(
    keys: frozenset[str], directory: Path, ms: MediaSource, *, dry_run: bool
) -> tuple[str, ...]:
    files = find_files_by_key(set(keys), directory, ms.key_fn) if keys else []
    delete_files(directory, files, dry_run=dry_run)
    return tuple(files)


def apply_rm_upstream(
    album_dir: Path, plan: RmUpstreamPlan, *, dry_run: bool
) -> RmUpstreamResult:
    """Delete every variant of the planned keys, browsable and archive alike."""
    ms = plan.ms
    images = plan.image_keys
    videos = plan.video_keys
    return RmUpstreamResult(
        heic=RmUpstreamHeicResult(
            removed_jpeg=_delete_keys(
                images, album_dir / ms.jpg_dir, ms, dry_run=dry_run
            ),
            removed_browsable=_delete_keys(
                images, album_dir / ms.img_dir, ms, dry_run=dry_run
            ),
            removed_rendered=_delete_keys(
                images, album_dir / ms.edit_img_dir, ms, dry_run=dry_run
            ),
            removed_orig=_delete_keys(
                images, album_dir / ms.orig_img_dir, ms, dry_run=dry_run
            ),
        ),
        mov=RmUpstreamMovResult(
            removed_rendered=_delete_keys(
                videos, album_dir / ms.edit_vid_dir, ms, dry_run=dry_run
            ),
            removed_orig=_delete_keys(
                videos, album_dir / ms.orig_vid_dir, ms, dry_run=dry_run
            ),
        ),
        skipped=plan.skipped,
    )


def rm_upstream(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> RmUpstreamResult:
    """Propagate deletions from browsable dirs to archive dirs.

    Works for both iOS and std media sources.

    Images: deletions detected from {name}-jpg or {name}-img are
    propagated to {name}-jpg, {name}-img, edit-img, and orig-img.

    Videos: files missing from {name}-vid (relative to orig-vid) are
    removed from edit-vid and orig-vid.

    See the module docstring for when a directory is ignored as a signal and
    when the operation is refused (:class:`RmUpstreamRefusedError`).
    """
    plan = plan_rm_upstream(album_dir, ms, force=force)
    check_rm_upstream_plans([plan], force=force)
    return apply_rm_upstream(album_dir, plan, dry_run=dry_run)
