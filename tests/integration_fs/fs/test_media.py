"""Tests for photree.fs.media module (generic key-function-based matching)."""

from pathlib import Path

from photree.album.store.media_sources import (
    dedup_media_dict,
    find_files_by_key,
    group_by_key,
    img_number,
    pick_media_priority,
)
from photree.album.store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS, _stem_key


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    """Create a directory with the given filenames."""
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


# ---------------------------------------------------------------------------
# group_by_key
# ---------------------------------------------------------------------------


class TestGroupByKey:
    def test_groups_by_img_number(self) -> None:
        files = ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC"]
        result = group_by_key(files, IMG_EXTENSIONS, img_number)
        assert result == {
            "0001": ["IMG_0001.HEIC"],
            "0002": ["IMG_0002.HEIC"],
        }

    def test_groups_by_stem(self) -> None:
        files = ["sunset.heic", "sunset.jpg", "beach.png"]
        result = group_by_key(files, IMG_EXTENSIONS, _stem_key)
        assert result == {
            "sunset": ["sunset.heic", "sunset.jpg"],
            "beach": ["beach.png"],
        }

    def test_filters_by_media_extensions(self) -> None:
        files = ["sunset.heic", "sunset.aae", "notes.txt"]
        result = group_by_key(files, IMG_EXTENSIONS, _stem_key)
        assert result == {"sunset": ["sunset.heic"]}

    def test_empty_input(self) -> None:
        result = group_by_key([], IMG_EXTENSIONS, _stem_key)
        assert result == {}

    def test_video_extensions(self) -> None:
        files = ["clip.mov", "clip.mp4", "clip.txt"]
        result = group_by_key(files, VID_EXTENSIONS, _stem_key)
        assert result == {"clip": ["clip.mov", "clip.mp4"]}


# ---------------------------------------------------------------------------
# dedup_media_dict
# ---------------------------------------------------------------------------


class TestDedupMediaDict:
    def test_dedup_by_img_number_prefers_heic(self) -> None:
        files = ["IMG_0001.HEIC", "IMG_0001.JPG"]
        result = dedup_media_dict(files, IMG_EXTENSIONS, img_number)
        assert result == {"0001": "IMG_0001.HEIC"}

    def test_dedup_by_img_number_prefers_dng_over_heic(self) -> None:
        files = ["IMG_0001.DNG", "IMG_0001.HEIC"]
        result = dedup_media_dict(files, IMG_EXTENSIONS, img_number)
        assert result == {"0001": "IMG_0001.DNG"}

    def test_dedup_by_stem_prefers_heic(self) -> None:
        files = ["sunset.heic", "sunset.jpg"]
        result = dedup_media_dict(files, IMG_EXTENSIONS, _stem_key)
        assert result == {"sunset": "sunset.heic"}

    def test_dedup_by_stem_prefers_dng_over_heic(self) -> None:
        files = ["sunset.dng", "sunset.heic"]
        result = dedup_media_dict(files, IMG_EXTENSIONS, _stem_key)
        assert result == {"sunset": "sunset.dng"}

    def test_single_file_per_key(self) -> None:
        files = ["sunset.heic", "beach.png"]
        result = dedup_media_dict(files, IMG_EXTENSIONS, _stem_key)
        assert result == {"sunset": "sunset.heic", "beach": "beach.png"}

    def test_filters_non_media(self) -> None:
        files = ["sunset.heic", "sunset.aae"]
        result = dedup_media_dict(files, IMG_EXTENSIONS, _stem_key)
        assert result == {"sunset": "sunset.heic"}


# ---------------------------------------------------------------------------
# find_files_by_key
# ---------------------------------------------------------------------------


class TestFindFilesByKey:
    def test_finds_by_img_number(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC"],
        )
        result = find_files_by_key({"0001"}, tmp_path, img_number)
        assert result == ["IMG_0001.AAE", "IMG_0001.HEIC"]

    def test_finds_by_stem(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path,
            ["sunset.heic", "sunset.jpg", "beach.png"],
        )
        result = find_files_by_key({"sunset"}, tmp_path, _stem_key)
        assert result == ["sunset.heic", "sunset.jpg"]

    def test_multiple_keys(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path,
            ["sunset.heic", "beach.png", "mountains.jpg"],
        )
        result = find_files_by_key({"sunset", "beach"}, tmp_path, _stem_key)
        assert result == ["beach.png", "sunset.heic"]

    def test_no_matches(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path, ["sunset.heic"])
        result = find_files_by_key({"unknown"}, tmp_path, _stem_key)
        assert result == []

    def test_missing_directory(self, tmp_path: Path) -> None:
        result = find_files_by_key({"sunset"}, tmp_path / "nonexistent", _stem_key)
        assert result == []


# ---------------------------------------------------------------------------
# pick_media_priority
# ---------------------------------------------------------------------------


class TestPickMediaPriority:
    def test_prefers_dng(self) -> None:
        assert pick_media_priority(["sunset.heic", "sunset.dng"]) == "sunset.dng"

    def test_prefers_heic_over_jpg(self) -> None:
        assert pick_media_priority(["sunset.jpg", "sunset.heic"]) == "sunset.heic"

    def test_dng_over_heic(self) -> None:
        assert (
            pick_media_priority(["sunset.heic", "sunset.dng", "sunset.jpg"])
            == "sunset.dng"
        )

    def test_fallback_to_first(self) -> None:
        assert pick_media_priority(["sunset.jpg", "sunset.png"]) == "sunset.jpg"

    def test_single_candidate(self) -> None:
        assert pick_media_priority(["sunset.heic"]) == "sunset.heic"
