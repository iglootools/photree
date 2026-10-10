"""Regression tests for album-core bugs: stale derived files, EXIF cache paths,
invalid dates, corrupt metadata, and media source name conflicts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from photree.album.browsable import refresh_browsable_dir
from photree.album.check import run_album_check
from photree.album.check.output import format_album_preflight_checks
from photree.album.exif_cache.protocol import (
    EXIF_CACHE_VERSION,
    ExifCache,
    ExifCacheEntry,
)
from photree.album.exif_cache.refresh import refresh_exif_cache
from photree.album.exif_cache.store import (
    cache_path,
    load_exif_cache,
    save_exif_cache,
)
from photree.album.exif_date_check import _try_read_from_cache, check_exif_date_match
from photree.album.faces.protocol import FaceProcessedKey, FaceProcessingState
from photree.album.faces.store import load_face_state, save_face_state
from photree.album.formats import IMG_EXTENSIONS
from photree.album.jpeg import (
    JpegAction,
    jpeg_action,
    jpeg_name,
    noop_convert_single,
    refresh_jpeg_dir,
)
from photree.album.naming import NamingIssueCode, check_album_naming
from photree.album.refresh import refresh_media_metadata
from photree.album.store.album_discovery import has_media_sources
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from photree.album.store.media_sources_discovery import (
    MediaSourceConflictError,
    discover_media_sources,
    find_media_source_conflicts,
)
from photree.albums.cmd_handler.check import batch_check
from photree.common.sips import SipsError
from photree.fsprotocol import InvalidMetadataError, LinkMode


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _names(directory: Path) -> set[str]:
    return {f.name for f in directory.iterdir()} if directory.is_dir() else set()


# ---------------------------------------------------------------------------
# JPEG refresh
# ---------------------------------------------------------------------------


class TestJpegRefresh:
    def test_sips_error_on_sequential_path_is_recorded(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "IMG_0001.HEIC")

        def failing_sips(s: Path, d: Path, *, dry_run: bool) -> Path | None:
            raise SipsError(path=s, returncode=1, stderr="not an image")

        result = refresh_jpeg_dir(src, dst, convert_file=failing_sips)

        assert [f.filename for f in result.failed] == ["IMG_0001.HEIC"]
        assert "not an image" in result.failed[0].reason

    @pytest.mark.parametrize("max_workers", [None, 4])
    def test_skipped_file_is_not_reported_as_failure(
        self, tmp_path: Path, max_workers: int | None
    ) -> None:
        """Both paths report a deliberately skipped file the same way."""
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "IMG_0001.HEIC")
        _write(src / "IMG_0001.MOV")  # Live Photo video: no JPEG variant
        ends: list[tuple[str, bool]] = []

        result = refresh_jpeg_dir(
            src,
            dst,
            convert_file=noop_convert_single,
            max_workers=max_workers,
            on_file_end=lambda name, ok: ends.append((name, ok)),
        )

        assert result.success
        assert result.skipped == 2
        assert ends == [("IMG_0001.HEIC", True)]

    def test_parallel_path_uses_the_given_converter(self, tmp_path: Path) -> None:
        """Parallelism is chosen by max_workers alone, never by converter identity."""
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "a.jpg")
        _write(src / "b.jpg")
        calls: list[str] = []

        def recording(s: Path, d: Path, *, dry_run: bool) -> Path | None:
            calls.append(s.name)
            return d / s.name

        result = refresh_jpeg_dir(src, dst, convert_file=recording, max_workers=4)

        assert sorted(calls) == ["a.jpg", "b.jpg"]
        assert result.copied == 2

    @pytest.mark.parametrize("src_exists", [True, False])
    def test_stale_jpegs_cleared_when_source_empty(
        self, tmp_path: Path, src_exists: bool
    ) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        if src_exists:
            src.mkdir()
        _write(dst / "stale.jpg")

        refresh_jpeg_dir(src, dst)

        assert _names(dst) == set()

    def test_classification(self) -> None:
        assert jpeg_action("IMG_0001.HEIC") == JpegAction.CONVERT
        assert jpeg_action("IMG_0001.png") == JpegAction.COPY
        assert jpeg_action("IMG_0001.MOV") == JpegAction.SKIP
        assert jpeg_name("IMG_0001.DNG") == "IMG_0001.jpg"
        assert jpeg_name("IMG_0001.png") == "IMG_0001.png"
        assert jpeg_name("IMG_0001.MOV") is None


class TestBrowsableRefresh:
    def test_stale_files_cleared_when_archive_empty(self, tmp_path: Path) -> None:
        orig, edit, browsable = tmp_path / "orig", tmp_path / "edit", tmp_path / "img"
        orig.mkdir()
        _write(browsable / "IMG_0001.HEIC")

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=MAIN_MEDIA_SOURCE.key_fn,
        )

        assert result.copied == 0
        assert _names(browsable) == set()


# ---------------------------------------------------------------------------
# Naming: invalid calendar dates
# ---------------------------------------------------------------------------


class TestInvalidDates:
    @pytest.mark.parametrize(
        "name",
        [
            "2024-13-45 - Title",
            "2024-02-30 - Title",
            "2024-13 - Title",
            "2024-08--2024-07 - Backwards",
        ],
    )
    def test_invalid_date_is_a_naming_issue(self, name: str) -> None:
        codes = [i.code for i in check_album_naming(name)]
        assert NamingIssueCode.INVALID_DATE in codes

    def test_valid_dates_have_no_date_issue(self) -> None:
        for name in ("2024-02-29 - Leap", "2024-07--2024-08-03 - Mixed", "2024 - Y"):
            assert check_album_naming(name) == ()

    def test_exif_check_skipped_for_invalid_date(self, tmp_path: Path) -> None:
        assert check_exif_date_match(tmp_path, "2024-02-30") is None


# ---------------------------------------------------------------------------
# EXIF cache: scoped keys and relative paths
# ---------------------------------------------------------------------------


class _FakeExifTool:
    """Stands in for ExifToolHelper: one fixed timestamp per file."""

    def __init__(self, timestamp: str) -> None:
        self.timestamp = timestamp

    def get_tags(self, files: list[str], tags: list[str]) -> list[dict[str, object]]:
        return [{"EXIF:DateTimeOriginal": self.timestamp} for _ in files]


def _album_with_same_stem_photo_and_video(album: Path) -> None:
    ms = MAIN_MEDIA_SOURCE
    _write(album / ms.orig_img_dir / "clip.HEIC")
    _write(album / ms.orig_vid_dir / "clip.MOV")
    _write(album / ms.jpg_dir / "clip.jpg")
    _write(album / ms.vid_dir / "clip.MOV")


class TestExifCachePaths:
    def test_same_stem_photo_and_video_do_not_collide(self, tmp_path: Path) -> None:
        _album_with_same_stem_photo_and_video(tmp_path)

        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2024:07:14 10:00:00"),  # type: ignore[arg-type]
        )

        cache = load_exif_cache(tmp_path, "main")
        assert cache is not None and cache.is_current
        assert {e.file_name for e in cache.files.values()} == {
            "main-jpg/clip.jpg",
            "main-vid/clip.MOV",
        }

    def test_mismatching_video_reported_under_its_own_dir(self, tmp_path: Path) -> None:
        _album_with_same_stem_photo_and_video(tmp_path)
        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2023:01:01 10:00:00"),  # type: ignore[arg-type]
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
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        refresh_exif_cache(
            tmp_path,
            exiftool=_FakeExifTool("2024:07:14 10:00:00"),  # type: ignore[arg-type]
        )

        cache = load_exif_cache(tmp_path, "main")
        assert cache is not None
        assert cache.version == EXIF_CACHE_VERSION
        assert "clip" not in cache.files
        assert set(cache.files) == {"main-jpg/clip", "main-vid/clip"}

    def test_cached_offset_timestamps_are_naive_wall_clock(
        self, tmp_path: Path
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

        cached = _try_read_from_cache(tmp_path)
        check = check_exif_date_match(tmp_path, "2024-07-14")

        assert cached is not None
        assert all(ts.tzinfo is None for _, ts in cached)
        assert datetime(2024, 7, 14, 23, 30) in {ts for _, ts in cached}
        assert check is not None
        assert check.mismatches == ()


# ---------------------------------------------------------------------------
# Corrupt metadata is never treated as absent
# ---------------------------------------------------------------------------


class TestCorruptMetadata:
    def test_corrupt_media_ids_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        refresh_media_metadata(tmp_path)
        ids_file = tmp_path / ".photree/media-ids/main.yaml"
        ids_file.write_text("images: [unterminated", encoding="utf-8")

        with pytest.raises(InvalidMetadataError) as exc_info:
            load_media_metadata(tmp_path)
        assert exc_info.value.path == ids_file

        # ...and a refresh must not silently mint fresh UUIDs over it.
        with pytest.raises(InvalidMetadataError):
            refresh_media_metadata(tmp_path)

    def test_corrupt_exif_cache_raises(self, tmp_path: Path) -> None:
        _write(cache_path(tmp_path, "main"), "")
        with pytest.raises(InvalidMetadataError):
            load_exif_cache(tmp_path, "main")

    def test_corrupt_face_state_raises(self, tmp_path: Path) -> None:
        save_face_state(
            tmp_path,
            "main",
            FaceProcessingState(
                processed_keys={
                    "0001": FaceProcessedKey(
                        mtime=1.0,
                        file_name="IMG_0001.HEIC",
                        face_count=0,
                        orig_width=1,
                        orig_height=1,
                        thumb_width=1,
                        thumb_height=1,
                    )
                }
            ),
        )
        state_file = tmp_path / ".photree/cache/faces/main.yaml"
        state_file.write_text("- not a mapping\n", encoding="utf-8")

        with pytest.raises(InvalidMetadataError):
            load_face_state(tmp_path, "main")


# ---------------------------------------------------------------------------
# Media source name conflicts
# ---------------------------------------------------------------------------


class TestMediaSourceConflicts:
    def test_ios_and_std_with_same_name_conflict(self, tmp_path: Path) -> None:
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        _write(tmp_path / "std-main/orig-img/DSC_0001.JPG")
        _write(tmp_path / "std-nelu/orig-img/DSC_0002.JPG")

        assert find_media_source_conflicts(tmp_path) == ("main",)
        with pytest.raises(MediaSourceConflictError) as exc_info:
            discover_media_sources(tmp_path)
        assert exc_info.value.names == ("main",)
        assert exc_info.value.album_dir == tmp_path

    def test_discovery_still_finds_conflicted_album(self, tmp_path: Path) -> None:
        """Album discovery must not crash a whole batch on one bad album."""
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        _write(tmp_path / "std-main/orig-img/DSC_0001.JPG")

        assert has_media_sources(tmp_path)

    def test_check_reports_conflict_instead_of_raising(self, tmp_path: Path) -> None:
        """A batch check must keep going: the clash is a failed check."""
        album = tmp_path / "2024-07-14 - Trip"
        _write(album / "ios-main/orig-img/IMG_0001.HEIC")
        _write(album / "std-main/orig-img/DSC_0001.JPG")

        result = run_album_check(
            album, sips_available=True, exiftool=None, link_mode=LinkMode.HARDLINK
        )

        assert result.media_source_conflicts == ("main",)
        assert not result.success
        assert "media source conflict" in result.error_labels
        assert result.naming is not None and result.naming.success
        assert "ios-<name>/ and std-<name>/ both present for: main" in (
            format_album_preflight_checks(result)
        )

    def test_batch_check_continues_past_conflict(self, tmp_path: Path) -> None:
        conflicted = tmp_path / "2024-07-14 - Trip"
        _write(conflicted / "ios-main/orig-img/IMG_0001.HEIC")
        _write(conflicted / "std-main/orig-img/DSC_0001.JPG")
        healthy = tmp_path / "2024-07-15 - Next"
        _write(healthy / "ios-main/orig-img/IMG_0002.HEIC")
        ends: list[tuple[str, bool, tuple[str, ...]]] = []

        batch_check(
            [conflicted, healthy],
            sips_available=True,
            link_mode=LinkMode.HARDLINK,
            check_naming=False,
            on_end=lambda name, ok, errors, _warnings: ends.append(
                (name, ok, tuple(errors))
            ),
        )

        assert len(ends) == 2
        assert ends[0][:2] == (conflicted.name, False)
        assert "media source conflict" in ends[0][2]

    def test_distinct_names_do_not_conflict(self, tmp_path: Path) -> None:
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        _write(tmp_path / "std-nelu/orig-img/DSC_0001.JPG")

        assert find_media_source_conflicts(tmp_path) == ()
        assert [ms.name for ms in discover_media_sources(tmp_path)] == ["main", "nelu"]


# ---------------------------------------------------------------------------
# Media IDs: injectable generator
# ---------------------------------------------------------------------------


def test_media_ids_use_injected_generator(tmp_path: Path) -> None:
    _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
    _write(tmp_path / "ios-main/orig-vid/IMG_0002.MOV")
    ids = iter(["id-image", "id-video"])

    refresh_media_metadata(tmp_path, new_id=lambda: next(ids))

    meta = load_media_metadata(tmp_path)
    assert meta is not None
    assert meta.media_sources["main"].images == {"id-image": "0001"}
    assert meta.media_sources["main"].videos == {"id-video": "0002"}
