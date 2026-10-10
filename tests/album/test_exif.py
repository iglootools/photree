"""Tests for album-specific EXIF helpers and generic common.exif functions."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from photree.album.exif import _TIMESTAMP_TAGS
from photree.common.exif import (
    ExifToolError,
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
    not shutil.which("exiftool"), reason="exiftool not installed"
)


def _extract_timestamp(metadata: dict[str, object]) -> datetime | None:
    """Test helper: extract_timestamp bound to the project's tag priority."""
    return extract_timestamp(metadata, _TIMESTAMP_TAGS)


# ---------------------------------------------------------------------------
# extract_timestamp (with project's _TIMESTAMP_TAGS)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# try_start_exiftool (from common.exif)
# ---------------------------------------------------------------------------


class TestTryStartExiftool:
    def test_returns_none_when_not_installed(self) -> None:
        assert try_start_exiftool(which=lambda _name: None) is None

    @pytest.mark.skipif(not shutil.which("exiftool"), reason="exiftool not installed")
    def test_returns_helper_when_installed(self) -> None:
        et = try_start_exiftool()
        assert et is not None
        et.__exit__(None, None, None)


class TestExiftoolSession:
    def test_disabled_yields_none(self) -> None:
        with exiftool_session(enabled=False) as et:
            assert et is None

    def test_not_installed_yields_none(self) -> None:
        with exiftool_session(which=lambda _name: None) as et:
            assert et is None


# ---------------------------------------------------------------------------
# read_exif_timestamps (from common.exif)
# ---------------------------------------------------------------------------


class TestReadExifTimestamps:
    def test_empty_files(self) -> None:
        assert read_exif_timestamps([], _TIMESTAMP_TAGS) == []


# ---------------------------------------------------------------------------
# parse_timestamp — naive wall-clock policy
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_offset_dropped_keeping_wall_clock(self) -> None:
        assert parse_timestamp("2024:07:20 23:30:00+09:00") == datetime(
            2024, 7, 20, 23, 30, 0
        )

    def test_mixed_offset_and_naive_values_are_comparable(self) -> None:
        """Regression: min() over aware + naive values raised TypeError."""
        parsed = [
            parse_timestamp("2024:07:20 13:55:20-06:00"),
            parse_timestamp("2024:07:20 10:00:00"),
        ]
        assert min(ts for ts in parsed if ts is not None) == datetime(
            2024, 7, 20, 10, 0, 0
        )

    def test_unparseable(self) -> None:
        assert parse_timestamp("nope") is None


# ---------------------------------------------------------------------------
# EXIF writing (real exiftool)
# ---------------------------------------------------------------------------


def _jpeg(path: Path, timestamp: str | None = "2024:07:20 13:55:20") -> Path:
    import cv2
    import numpy as np

    cv2.imwrite(str(path), np.zeros((8, 8, 3), dtype=np.uint8))
    if timestamp is not None:
        set_exif_date_time([path], timestamp.replace(":", "-", 2).replace(" ", "T"))
    return path


def _read(path: Path) -> datetime | None:
    [ts] = read_exif_timestamps([path], _TIMESTAMP_TAGS) or [None]
    return ts


@requires_exiftool
class TestExifWriting:
    def test_write_exif_date_keeps_time(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")
        changes = write_exif_date([img], "2023-01-02", _TIMESTAMP_TAGS)
        assert [(c.original, c.new_value) for c in changes] == [
            ("2024:07:20 13:55:20", "2023:01:02 13:55:20")
        ]
        assert _read(img) == datetime(2023, 1, 2, 13, 55, 20)

    def test_write_exif_date_skips_files_without_timestamp(
        self, tmp_path: Path
    ) -> None:
        img = _jpeg(tmp_path / "a.jpg", timestamp=None)
        assert write_exif_date([img], "2023-01-02", _TIMESTAMP_TAGS) == ()

    def test_shift_date_and_time_both_directions(self, tmp_path: Path) -> None:
        img = _jpeg(tmp_path / "a.jpg")
        shift_exif_date([img], -1)
        shift_exif_time([img], 3)
        assert _read(img) == datetime(2024, 7, 19, 16, 55, 20)

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
            write_exif_date([missing], "2023-01-02", _TIMESTAMP_TAGS)
        assert exc_info.value.paths == (missing,)
