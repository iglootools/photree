"""
Live Photo detection and browsable directory augmentation.

iOS Live Photos consist of an image file coupled with a short .MOV video
file sharing the same image number. Both files are stored together in
``orig-img/`` as a unit.

Live Photos are primarily an iOS feature. This module is only applied to
iOS media sources.
"""

from pathlib import Path

from photree.album.browsable import place_file
from photree.album.store.file_matching import dedup_media_dict
from photree.album.store.media_source import KeyFn
from photree.common.fs import list_files
from photree.foundation.linking import LinkMode


def detect_live_photo_keys(
    directory: Path,
    img_extensions: frozenset[str],
    vid_extensions: frozenset[str],
    key_fn: KeyFn,
) -> frozenset[str]:
    """
    Return the keys in *directory* that have both an image and a video.

    Those are the Live Photos; an absent *directory* has none.
    """
    if not directory.is_dir():
        return frozenset()
    files = list_files(directory)
    img_keys = set(dedup_media_dict(files, img_extensions, key_fn).keys())
    vid_keys = set(dedup_media_dict(files, vid_extensions, key_fn).keys())
    return frozenset(img_keys & vid_keys)


def compute_live_photo_videos(
    orig_dir: Path,
    edit_dir: Path,
    vid_extensions: frozenset[str],
    key_fn: KeyFn,
) -> list[tuple[str, Path]]:
    """
    Return the Live Photo videos to place in the browsable img dir.

    For each video key in *orig_dir*, picks the edited variant from
    *edit_dir* when available, otherwise the original.

    Returns ``(filename, source_dir)`` pairs sorted by filename.
    """
    if not orig_dir.is_dir():
        return []

    orig_vids = dedup_media_dict(list_files(orig_dir), vid_extensions, key_fn)
    edit_vids = (
        dedup_media_dict(list_files(edit_dir), vid_extensions, key_fn)
        if edit_dir.is_dir()
        else {}
    )

    return sorted(
        [
            *((edit_vids[key], edit_dir) for key in orig_vids if key in edit_vids),
            *(
                (orig_name, orig_dir)
                for key, orig_name in orig_vids.items()
                if key not in edit_vids
            ),
        ],
        key=lambda pair: pair[0],
    )


def augment_browsable_img_with_live_photo_videos(
    orig_img_dir: Path,
    edit_img_dir: Path,
    browsable_img_dir: Path,
    *,
    vid_extensions: frozenset[str],
    key_fn: KeyFn,
    link_mode: LinkMode,
    dry_run: bool,
) -> int:
    """Place Live Photo videos in the browsable img dir, returning how many."""
    videos = compute_live_photo_videos(
        orig_img_dir,
        edit_img_dir,
        vid_extensions,
        key_fn,
    )
    if not videos or not browsable_img_dir.is_dir():
        return 0

    for filename, source_dir in videos:
        if not dry_run:
            place_file(source_dir / filename, browsable_img_dir / filename, link_mode)

    return len(videos)
