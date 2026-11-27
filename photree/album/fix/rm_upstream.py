"""
rm-upstream fix operation.

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
  ``{name}-img/`` or ``{name}-vid/`` — is refused unless ``force`` is set;
- a source whose signal directory the last refresh left incomplete (it
  failed to convert some JPEGs, or was interrupted while rebuilding the
  directory: see :data:`~photree.album.browsable.INCOMPLETE_MARKER`) is
  refused, even with ``force``: its gaps are files refresh never wrote, not
  files the user deleted, and ``force`` only vouches for the user's own
  deletions.

Directories are compared with their source by item key, never by filename: a
browsable directory older than the archive (an edit added or moved since the
last refresh renames the item's browsable file) still holds every item the
user kept, and must not read as deletions.

Every source is planned before anything is deleted, so a refusal leaves the
album untouched.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album import browsable as browsable_module
from photree.album.fix.helpers import require_archive
from photree.album.formats import IMG_EXTENSIONS
from photree.album.jpeg import jpeg_name
from photree.album.store.file_matching import find_files_by_key
from photree.album.store.media_source import MediaSource
from photree.common.fs import delete_files, list_files


class MediaKind(StrEnum):
    """Which half of an archive, images or videos, a refusal is about."""

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
    """
    Propagating deletions would remove every item of an archive.

    Raised before anything is deleted. Pass ``force`` (``--force``) to proceed.
    """

    def __init__(self, media_source: str, kind: MediaKind, key_count: int) -> None:
        """Build the error from the media source, the media kind and its key count."""
        self.media_source = media_source
        self.kind = kind
        self.key_count = key_count
        super().__init__(
            f"rm-upstream would delete all {key_count} {kind} of media source "
            f"{media_source!r}; refusing without --force",
        )


class RmUpstreamIncompleteSignalError(ValueError):
    """
    A signal directory was left incomplete by a failed or interrupted refresh.

    Raised before anything is deleted, whatever ``force`` says: the files
    missing from *directories* were never written, so they are not deletions.
    Running ``photree album refresh`` rebuilds the directories.
    """

    def __init__(self, media_source: str, directories: tuple[str, ...]) -> None:
        """Build the error from the media source and its incomplete directories."""
        self.media_source = media_source
        self.directories = directories
        super().__init__(
            f"{', '.join(directories)} of media source {media_source!r} "
            "were left incomplete by a failed or interrupted refresh; run "
            "'photree album refresh' before --rm-upstream",
        )


@dataclass(frozen=True)
class RmUpstreamHeicResult:
    """The image files rm-upstream removed, per directory: jpg, img, edit and orig."""

    removed_jpeg: tuple[str, ...]
    removed_browsable: tuple[str, ...]
    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamMovResult:
    """The video files rm-upstream removed, per directory: edit and orig."""

    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamResult:
    """The outcome of rm-upstream for one media source, with the signals skipped."""

    heic: RmUpstreamHeicResult
    mov: RmUpstreamMovResult
    skipped: tuple[RmUpstreamSkip, ...] = ()


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
    incomplete_dirs: tuple[str, ...]

    def incomplete(self) -> RmUpstreamIncompleteSignalError | None:
        """Return the error to raise if a signal dir is incomplete, else None."""
        return (
            RmUpstreamIncompleteSignalError(self.ms.name, self.incomplete_dirs)
            if self.incomplete_dirs
            else None
        )

    def refusal(self) -> RmUpstreamRefusedError | None:
        """Return the error to raise if this plan would empty an archive, else None."""
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
    """
    Return why *directory* cannot be trusted as a deletion signal, if so.

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
    expected: frozenset[str],
    present: frozenset[str],
    force: bool,
    require_expected: bool = False,
) -> _Signal:
    """Return the *expected* keys missing from *present*, or why the dir is skipped."""
    skip = _signal_skip(
        ms,
        directory,
        subdir,
        expected=expected,
        present=present,
        require_expected=require_expected,
        force=force,
    )
    return _Signal(skip=skip) if skip is not None else _Signal(keys=expected - present)


def _keys_in(directory: Path, ms: MediaSource) -> frozenset[str]:
    return frozenset(ms.key_fn(f) for f in list_files(directory))


def _plan_images(
    album_dir: Path,
    ms: MediaSource,
    *,
    force: bool,
) -> tuple[_Signal, _Signal]:
    """Signals from ``{name}-img/`` (vs. the archive) and ``{name}-jpg/`` (vs. img)."""
    key_fn = ms.key_fn
    img_files = list_files(album_dir / ms.img_dir)
    archive_keys = frozenset(
        key_fn(filename)
        for filename, _ in browsable_module.compute_browsable_files(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            IMG_EXTENSIONS,
            key_fn,
        )
    )
    keys_with_jpeg = frozenset(key_fn(f) for f in img_files if jpeg_name(f) is not None)
    return (
        _deleted_keys(
            ms,
            album_dir / ms.img_dir,
            ms.img_dir,
            expected=archive_keys,
            present=frozenset(key_fn(f) for f in img_files),
            force=force,
        ),
        _deleted_keys(
            ms,
            album_dir / ms.jpg_dir,
            ms.jpg_dir,
            expected=keys_with_jpeg,
            present=_keys_in(album_dir / ms.jpg_dir, ms),
            force=force,
            require_expected=True,
        ),
    )


def _plan_videos(album_dir: Path, ms: MediaSource, *, force: bool) -> _Signal:
    """
    Signal from ``{name}-vid/``, compared by key with ``orig-vid/``.

    By key, so that edited videos (e.g. ``IMG_E0001.MOV``) are matched to
    their originals (``IMG_0001.MOV``).
    """
    return _deleted_keys(
        ms,
        album_dir / ms.vid_dir,
        ms.vid_dir,
        expected=_keys_in(album_dir / ms.orig_vid_dir, ms),
        present=_keys_in(album_dir / ms.vid_dir, ms),
        force=force,
    )


def plan_rm_upstream(
    album_dir: Path,
    ms: MediaSource,
    *,
    force: bool = False,
) -> RmUpstreamPlan:
    """
    Plan the keys to delete from *ms*'s browsable directories, without deleting.

    With *force*, a ``{name}-jpg/`` holding none of its expected JPEGs is still
    used as a signal. Raises
    :class:`~photree.album.fix.helpers.MissingArchiveError` when a std source
    has no archive directory.
    """
    require_archive(album_dir, ms)
    from_img, from_jpg = _plan_images(album_dir, ms, force=force)
    from_vid = _plan_videos(album_dir, ms, force=force)
    signals = (from_img, from_jpg, from_vid)
    return RmUpstreamPlan(
        ms=ms,
        image_keys=from_img.keys | from_jpg.keys,
        video_keys=from_vid.keys,
        archive_image_keys=_keys_in(album_dir / ms.orig_img_dir, ms),
        archive_video_keys=_keys_in(album_dir / ms.orig_vid_dir, ms),
        skipped=tuple(sig.skip for sig in signals if sig.skip is not None),
        incomplete_dirs=tuple(
            subdir
            for subdir in (ms.img_dir, ms.jpg_dir, ms.vid_dir)
            if browsable_module.is_incomplete(album_dir / subdir)
        ),
    )


def check_rm_upstream_plans(plans: list[RmUpstreamPlan], *, force: bool) -> None:
    """
    Raise the first refusal among *plans*.

    :class:`RmUpstreamIncompleteSignalError` is raised whatever *force* says,
    :class:`RmUpstreamRefusedError` only without *force*.
    """
    incomplete = next(
        (err for plan in plans if (err := plan.incomplete()) is not None),
        None,
    )
    if incomplete is not None:
        raise incomplete
    refusal = next((err for plan in plans if (err := plan.refusal()) is not None), None)
    if refusal is not None and not force:
        raise refusal


def _delete_keys(
    keys: frozenset[str],
    directory: Path,
    ms: MediaSource,
    *,
    dry_run: bool,
) -> tuple[str, ...]:
    files = find_files_by_key(set(keys), directory, ms.key_fn) if keys else []
    delete_files(directory, files, dry_run=dry_run)
    return tuple(files)


def apply_rm_upstream(
    album_dir: Path,
    plan: RmUpstreamPlan,
    *,
    dry_run: bool,
) -> RmUpstreamResult:
    """Delete every variant of the planned keys, browsable and archive alike."""
    ms = plan.ms
    images = plan.image_keys
    videos = plan.video_keys
    return RmUpstreamResult(
        heic=RmUpstreamHeicResult(
            removed_jpeg=_delete_keys(
                images,
                album_dir / ms.jpg_dir,
                ms,
                dry_run=dry_run,
            ),
            removed_browsable=_delete_keys(
                images,
                album_dir / ms.img_dir,
                ms,
                dry_run=dry_run,
            ),
            removed_rendered=_delete_keys(
                images,
                album_dir / ms.edit_img_dir,
                ms,
                dry_run=dry_run,
            ),
            removed_orig=_delete_keys(
                images,
                album_dir / ms.orig_img_dir,
                ms,
                dry_run=dry_run,
            ),
        ),
        mov=RmUpstreamMovResult(
            removed_rendered=_delete_keys(
                videos,
                album_dir / ms.edit_vid_dir,
                ms,
                dry_run=dry_run,
            ),
            removed_orig=_delete_keys(
                videos,
                album_dir / ms.orig_vid_dir,
                ms,
                dry_run=dry_run,
            ),
        ),
        skipped=plan.skipped,
    )


def rm_upstream(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    dry_run: bool,
    force: bool,
) -> tuple[RmUpstreamResult, ...]:
    """
    Propagate the deletions in *media_sources*' browsable dirs to their archives.

    Images: deletions detected from {name}-jpg or {name}-img are
    propagated to {name}-jpg, {name}-img, edit-img, and orig-img.

    Videos: files missing from {name}-vid (relative to orig-vid) are
    removed from edit-vid and orig-vid.

    Every source is planned before anything is deleted, so one refusal
    (:class:`RmUpstreamRefusedError`) leaves the whole album untouched. See
    the module docstring for when a directory is ignored as a signal and when
    the operation is refused.
    """
    plans = [plan_rm_upstream(album_dir, ms, force=force) for ms in media_sources]
    check_rm_upstream_plans(plans, force=force)
    return tuple(apply_rm_upstream(album_dir, plan, dry_run=dry_run) for plan in plans)
