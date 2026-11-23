from datetime import datetime
from pathlib import Path

import pytest
import yaml

from photree.album.check.exif_date import check_exif_date_match, try_read_from_cache
from photree.album.exif_cache.protocol import (
    EXIF_CACHE_VERSION,
    ExifCache,
    ExifCacheEntry,
)
from photree.album.exif_cache.refresh import refresh_exif_cache
from photree.album.exif_cache.store import cache_path, load_exif_cache, save_exif_cache
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from photree.foundation.metadata_io import InvalidMetadataError
from tests.testkit import write_file


class _FakeExifTool:
    """Stands in for ExifToolHelper: one fixed timestamp per file."""

    def __init__(self, timestamp: str) -> None:
        self.timestamp = timestamp

    def get_tags(self, files: list[str], tags: list[str]) -> list[dict[str, object]]:  # noqa: ARG002 - ExifTagReader's signature
        return [{"EXIF:DateTimeOriginal": self.timestamp} for _ in files]


def _album_with_same_stem_photo_and_video(album: Path) -> None:
    ms = MAIN_MEDIA_SOURCE
    write_file(album / ms.orig_img_dir / "clip.HEIC")
    write_file(album / ms.orig_vid_dir / "clip.MOV")
    write_file(album / ms.jpg_dir / "clip.jpg")
    write_file(album / ms.vid_dir / "clip.MOV")


class TestExifCachePaths:
    def test_same_stem_photo_and_video_do_not_collide(self, tmp_path: Path) -> None:
        _album_with_same_stem_photo_and_video(tmp_path)

        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2024:07:14 10:00:00"),
        )

        cache = load_exif_cache(tmp_path, "main")
        assert cache is not None
        assert cache.is_current
        assert {e.file_name for e in cache.files.values()} == {
            "main-jpg/clip.jpg",
            "main-vid/clip.MOV",
        }

    def test_mismatching_video_reported_under_its_own_dir(self, tmp_path: Path) -> None:
        _album_with_same_stem_photo_and_video(tmp_path)
        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2023:01:01 10:00:00"),
        )

        check = check_exif_date_match(tmp_path, "2024-07-14")

        assert check is not None
        assert {m.file_name for m in check.mismatches} == {
            "main-jpg/clip.jpg",
            "main-vid/clip.MOV",
        }

    def test_old_cache_layout_is_rebuilt(self, tmp_path: Path) -> None:
        _album_with_same_stem_photo_and_video(tmp_path)
        old = cache_path(tmp_path, "main")
        old.parent.mkdir(parents=True)
        old.write_text(
            yaml.safe_dump(
                {
                    "files": {
                        "clip": {
                            "mtime": 0.0,
                            "file-name": "clip.MOV",
                            "timestamp": None,
                        },
                    },
                },
            ),
            encoding="utf-8",
        )

        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2024:07:14 10:00:00"),
        )

        cache = load_exif_cache(tmp_path, "main")
        assert cache is not None
        assert cache.version == EXIF_CACHE_VERSION
        assert "clip" not in cache.files
        assert set(cache.files) == {"main-jpg/clip", "main-vid/clip"}

    def test_cached_offset_timestamps_are_naive_wall_clock(
        self,
        tmp_path: Path,
    ) -> None:
        # A cache mixing an offset timestamp (CreationDate) with a naive one
        # must compare like a fresh exiftool read: wall-clock, offset dropped.
        _album_with_same_stem_photo_and_video(tmp_path)
        save_exif_cache(
            tmp_path,
            "main",
            ExifCache(
                version=EXIF_CACHE_VERSION,
                files={
                    "main-jpg/clip": ExifCacheEntry(
                        mtime=0.0,
                        file_name="main-jpg/clip.jpg",
                        timestamp="2024-07-14T10:00:00",
                    ),
                    "main-vid/clip": ExifCacheEntry(
                        mtime=0.0,
                        file_name="main-vid/clip.MOV",
                        timestamp="2024-07-14T23:30:00-06:00",
                    ),
                },
            ),
        )

        cached = try_read_from_cache(tmp_path)
        check = check_exif_date_match(tmp_path, "2024-07-14")

        assert cached is not None
        assert all(ts.tzinfo is None for _, ts in cached)
        assert datetime(2024, 7, 14, 23, 30) in {ts for _, ts in cached}
        assert check is not None
        assert check.mismatches == ()


class TestCorruptExifCache:
    def test_corrupt_exif_cache_raises_as_derived(self, tmp_path: Path) -> None:
        write_file(cache_path(tmp_path, "main"), "")
        with pytest.raises(InvalidMetadataError) as exc_info:
            load_exif_cache(tmp_path, "main")
        assert exc_info.value.derived

    def test_forced_refresh_replaces_corrupt_exif_cache(self, tmp_path: Path) -> None:
        _album_with_same_stem_photo_and_video(tmp_path)
        write_file(cache_path(tmp_path, "main"), "files: [unterminated")

        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2024:07:14 10:00:00"),
            force=True,
        )

        cache = load_exif_cache(tmp_path, "main")
        assert cache is not None
        assert set(cache.files) == {"main-jpg/clip", "main-vid/clip"}

    def test_forced_refresh_replaces_corrupt_empty_source_cache(
        self,
        tmp_path: Path,
    ) -> None:
        write_file(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(cache_path(tmp_path, "main"), "")

        refresh_exif_cache(tmp_path, exiftool=_FakeExifTool("unused"), force=True)

        cache = load_exif_cache(tmp_path, "main")
        assert cache is not None
        assert cache.files == {}
