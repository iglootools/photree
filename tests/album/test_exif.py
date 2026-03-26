"""Tests for photree.album.exif module."""

from __future__ import annotations

import shutil
from datetime import datetime
from unittest.mock import patch

import pytest

from photree.album.exif import (
    _extract_timestamp,
    read_exif_timestamps,
    try_start_exiftool,
)


# ---------------------------------------------------------------------------
# _extract_timestamp
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


# ---------------------------------------------------------------------------
# try_start_exiftool
# ---------------------------------------------------------------------------


class TestTryStartExiftool:
    def test_returns_none_when_not_installed(self) -> None:
        with patch("photree.album.exif.shutil.which", return_value=None):
            assert try_start_exiftool() is None

    @pytest.mark.skipif(not shutil.which("exiftool"), reason="exiftool not installed")
    def test_returns_helper_when_installed(self) -> None:
        et = try_start_exiftool()
        assert et is not None
        et.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# read_exif_timestamps
# ---------------------------------------------------------------------------


class TestReadExifTimestamps:
    def test_empty_files(self) -> None:
        assert read_exif_timestamps([]) == []
