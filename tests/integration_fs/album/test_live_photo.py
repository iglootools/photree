from pathlib import Path

from photree.album.live_photo import augment_browsable_img_with_live_photo_videos
from photree.album.store.media_source import ios_media_source
from photree.foundation.linking import LinkMode
from tests.testkit import file_names, write_files

_MS = ios_media_source("main")


def _augment(album: Path, *, dry_run: bool) -> int:
    return augment_browsable_img_with_live_photo_videos(
        album / _MS.orig_img_dir,
        album / _MS.edit_img_dir,
        album / _MS.img_dir,
        vid_extensions=_MS.vid_extensions,
        key_fn=_MS.key_fn,
        link_mode=LinkMode.COPY,
        dry_run=dry_run,
    )


class TestAugmentBrowsableImg:
    def test_places_live_photo_videos(self, tmp_path: Path) -> None:
        write_files(tmp_path / _MS.orig_img_dir, ["IMG_0001.JPG", "IMG_0001.MOV"])
        write_files(tmp_path / _MS.img_dir, ["IMG_0001.JPG"])

        assert _augment(tmp_path, dry_run=False) == 1
        assert file_names(tmp_path / _MS.img_dir) == {"IMG_0001.JPG", "IMG_0001.MOV"}

    def test_dry_run_counts_without_placing(self, tmp_path: Path) -> None:
        write_files(tmp_path / _MS.orig_img_dir, ["IMG_0001.JPG", "IMG_0001.MOV"])
        write_files(tmp_path / _MS.img_dir, ["IMG_0001.JPG"])

        assert _augment(tmp_path, dry_run=True) == 1
        assert file_names(tmp_path / _MS.img_dir) == {"IMG_0001.JPG"}
