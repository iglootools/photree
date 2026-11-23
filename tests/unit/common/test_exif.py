import shutil
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest

from photree.album.exif import TIMESTAMP_TAGS
from photree.common.exif import (
    ExifToolError,
    classify_failed_writes,
    exiftool_session,
    extract_timestamp,
    parse_timestamp,
    read_exif_timestamps,
    set_exif_date_time,
    shift_exif_date,
    shift_exif_time,
    try_start_exiftool,
    write_exif_date,
)

requires_exiftool = pytest.mark.skipif(
    not shutil.which("exiftool"),
    reason="exiftool not installed",
)


def _extract_timestamp(metadata: Mapping[str, object]) -> datetime | None:
    """Test helper: extract_timestamp bound to the project's tag priority."""
    return extract_timestamp(metadata, TIMESTAMP_TAGS)


class TestExtractTimestamp:
    def test_date_time_original(self) -> None:
        metadata = {
            "SourceFile": "test.jpg",
            "EXIF:DateTimeOriginal": "2024:06:15 14:30:00",
        }
        assert _extract_timestamp(metadata) == datetime(2024, 6, 15, 14, 30, 0)

    def test_create_date_fallback(self) -> None:
        metadata = {
            "SourceFile": "test.mov",
            "QuickTime:CreateDate": "2024:06:15 14:30:00",
        }
        assert _extract_timestamp(metadata) == datetime(2024, 6, 15, 14, 30, 0)

    def test_prefers_date_time_original_over_create_date(self) -> None:
        metadata = {
            "SourceFile": "test.jpg",
            "EXIF:DateTimeOriginal": "2024:06:15 10:00:00",
            "EXIF:CreateDate": "2024:06:15 14:30:00",
        }
        assert _extract_timestamp(metadata) == datetime(2024, 6, 15, 10, 0, 0)

    def test_empty_metadata(self) -> None:
        assert _extract_timestamp({"SourceFile": "test.jpg"}) is None

    def test_empty_value(self) -> None:
        metadata = {
            "SourceFile": "test.jpg",
            "EXIF:DateTimeOriginal": "",
        }
        assert _extract_timestamp(metadata) is None

    def test_invalid_date_format(self) -> None:
        metadata = {
            "SourceFile": "test.jpg",
            "EXIF:DateTimeOriginal": "not-a-date",
        }
        assert _extract_timestamp(metadata) is None

    def test_non_string_value(self) -> None:
        metadata = {
            "SourceFile": "test.jpg",
            "EXIF:DateTimeOriginal": 0,
        }
        assert _extract_timestamp(metadata) is None

    def test_creation_date_preferred_over_create_date(self) -> None:
        """QuickTime CreationDate (with timezone) is preferred for videos."""
        metadata = {
            "SourceFile": "test.mov",
            "QuickTime:CreationDate": "2024:07:20 13:55:20-06:00",
            "QuickTime:CreateDate": "2024:07:23 04:52:27",
        }
        ts = _extract_timestamp(metadata)
        assert ts is not None
        assert ts.date() == datetime(2024, 7, 20).date()

    def test_creation_date_with_timezone_parsed(self) -> None:
        metadata = {
            "SourceFile": "test.mov",
            "QuickTime:CreationDate": "2024:07:20 13:55:20-06:00",
        }
        ts = _extract_timestamp(metadata)
        assert ts is not None
        # Naive wall-clock policy: the offset is dropped, local time kept.
        assert ts == datetime(2024, 7, 20, 13, 55, 20)
        assert ts.tzinfo is None

    def test_creation_date_preferred_over_date_time_original(self) -> None:
        metadata = {
            "SourceFile": "test.mov",
            "QuickTime:CreationDate": "2024:07:20 13:55:20-06:00",
            "EXIF:DateTimeOriginal": "2024:07:23 04:52:27",
        }
        ts = _extract_timestamp(metadata)
        assert ts is not None
        assert ts.date() == datetime(2024, 7, 20).date()


class TestTryStartExiftool:
    def test_returns_none_when_not_installed(self) -> None:
        assert try_start_exiftool(which=lambda _name: None) is None

    @pytest.mark.skipif(not shutil.which("exiftool"), reason="exiftool not installed")
    def test_returns_helper_when_installed(self) -> None:
        et = try_start_exiftool()
        assert et is not None
        # PyExifTool leaves __exit__'s parameters unannotated.
        et.__exit__(None, None, None)  # pyright: ignore[reportUnknownMemberType]


class TestExiftoolSession:
    def test_disabled_yields_none(self) -> None:
        with exiftool_session(enabled=False) as et:
            assert et is None

    def test_not_installed_yields_none(self) -> None:
        with exiftool_session(which=lambda _name: None) as et:
            assert et is None


class TestReadExifTimestamps:
    def test_empty_files(self) -> None:
        assert read_exif_timestamps([], TIMESTAMP_TAGS) == []


class TestParseTimestamp:
    def test_offset_dropped_keeping_wall_clock(self) -> None:
        assert parse_timestamp("2024:07:20 23:30:00+09:00") == datetime(
            2024,
            7,
            20,
            23,
            30,
            0,
        )

    def test_mixed_offset_and_naive_values_are_comparable(self) -> None:
        """Regression: min() over aware + naive values raised TypeError."""
        parsed = [
            parse_timestamp("2024:07:20 13:55:20-06:00"),
            parse_timestamp("2024:07:20 10:00:00"),
        ]
        assert min(ts for ts in parsed if ts is not None) == datetime(
            2024,
            7,
            20,
            10,
            0,
            0,
        )

    def test_unparseable(self) -> None:
        assert parse_timestamp("nope") is None


def _jpeg(path: Path, timestamp: str | None = "2024:07:20 13:55:20") -> Path:
    cv2.imwrite(str(path), np.zeros((8, 8, 3), dtype=np.uint8))
    if timestamp is not None:
        set_exif_date_time([path], timestamp.replace(":", "-", 2).replace(" ", "T"))
    return path


def _read(path: Path) -> datetime | None:
    [ts] = read_exif_timestamps([path], TIMESTAMP_TAGS) or [None]
    return ts


@requires_exiftool
class TestExifWriting:
    def test_write_exif_date_keeps_time(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")
        changes = write_exif_date([img], "2023-01-02", TIMESTAMP_TAGS)
        assert [(c.original, c.new_value) for c in changes] == [
            ("2024:07:20 13:55:20", "2023:01:02 13:55:20"),
        ]
        assert _read(img) == datetime(2023, 1, 2, 13, 55, 20)

    def test_write_exif_date_keeps_each_files_own_time(self, tmp_path: Path) -> None:
        # All files go through one exiftool run, but each gets its own value.
        files = [
            _jpeg(tmp_path / "a.jpg", "2024:07:20 08:00:00"),
            _jpeg(tmp_path / "odd  name\\ #1.jpg", "2024:07:21 09:30:00"),
            _jpeg(tmp_path / "c.jpg", "2024:07:22 23:59:59"),
        ]

        write_exif_date(files, "2023-01-02", TIMESTAMP_TAGS)

        assert [_read(f) for f in files] == [
            datetime(2023, 1, 2, 8, 0, 0),
            datetime(2023, 1, 2, 9, 30, 0),
            datetime(2023, 1, 2, 23, 59, 59),
        ]

    def test_failed_write_names_only_its_file(self, tmp_path: Path) -> None:
        writable = _jpeg(tmp_path / "a.jpg")
        read_only = _jpeg(tmp_path / "b.jpg")
        read_only.chmod(0o444)

        with pytest.raises(ExifToolError) as exc_info:
            write_exif_date([read_only, writable], "2023-01-02", TIMESTAMP_TAGS)

        assert [p.name for p in exc_info.value.paths] == ["b.jpg"]
        assert _read(writable) == datetime(2023, 1, 2, 13, 55, 20)
        assert _read(read_only) == datetime(2024, 7, 20, 13, 55, 20)

    def test_write_exif_date_skips_files_without_timestamp(
        self,
        tmp_path: Path,
    ) -> None:
        img = _jpeg(tmp_path / "a.jpg", timestamp=None)
        assert write_exif_date([img], "2023-01-02", TIMESTAMP_TAGS) == ()

    def test_shift_date_and_time_both_directions(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")
        shift_exif_date([img], -1)
        shift_exif_time([img], 3)
        assert _read(img) == datetime(2024, 7, 19, 16, 55, 20)

    def test_write_keeps_hardlinked_copies_in_sync(self, tmp_path: Path) -> None:
        # A browsable dir hardlinks the archive: replacing the file with a new
        # inode would leave the browsable copy with the old date.
        img = _jpeg(tmp_path / "a.jpg")
        link = tmp_path / "b.jpg"
        link.hardlink_to(img)

        write_exif_date([img], "2023-01-02", TIMESTAMP_TAGS)

        assert img.stat().st_ino == link.stat().st_ino
        assert _read(link) == datetime(2023, 1, 2, 13, 55, 20)

    def test_path_starting_with_a_dash_is_a_file_not_an_option(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        # Path("./-AllDates=...") stringifies without its "./": exiftool must
        # still read it as a file, never as a tag assignment.
        chdir(tmp_path)
        dashed = _jpeg(Path("-AllDates=2000:01:01 00:00:00.jpg"))
        other = _jpeg(Path("b.jpg"))

        set_exif_date_time([dashed, other], "2023-01-02T03:04:05")

        assert _read(dashed) == datetime(2023, 1, 2, 3, 4, 5)
        assert _read(other) == datetime(2023, 1, 2, 3, 4, 5)

    def test_failed_write_raises_structured_error(self, tmp_path: Path) -> None:
        """Regression: failed writes used to be counted as updated."""
        not_media = tmp_path / "notes.txt"
        not_media.write_text("hello", encoding="utf-8")
        with pytest.raises(ExifToolError) as exc_info:
            shift_exif_date([not_media], 1)
        assert exc_info.value.paths == (not_media,)
        assert exc_info.value.returncode != 0
        assert exc_info.value.stderr

    def test_missing_file_raises_on_read(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.jpg"
        with pytest.raises(ExifToolError) as exc_info:
            write_exif_date([missing], "2023-01-02", TIMESTAMP_TAGS)
        assert exc_info.value.paths == (missing,)


_PATHS = (Path("a.jpg"), Path("b.jpg"), Path("c.jpg"))


class TestClassifyFailedWrites:
    def test_names_the_files_whose_status_is_not_zero(self) -> None:
        assert classify_failed_writes(_PATHS, ["0", "1", "0"], 1) == (Path("b.jpg"),)

    def test_no_failure_when_every_status_is_zero(self) -> None:
        assert classify_failed_writes(_PATHS, ["0", "0", "0"], 0) == ()

    def test_blames_every_file_when_statuses_are_missing(self) -> None:
        assert classify_failed_writes(_PATHS, ["0"], 1) == _PATHS

    def test_blames_every_file_when_status_is_not_expanded(self) -> None:
        assert classify_failed_writes(_PATHS, ["${status}"] * 3, 1) == _PATHS

    def test_no_failure_when_unattributable_but_exit_is_zero(self) -> None:
        assert classify_failed_writes(_PATHS, ["${status}"] * 3, 0) == ()
