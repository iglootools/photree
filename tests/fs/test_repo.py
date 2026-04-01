"""Tests for photree.fs.repo — media source discovery."""

from pathlib import Path

from photree.fs import MediaSourceType, std_media_source
from photree.fs.repo import (
    _is_std_source_dir,
    discover_media_sources,
)


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    """Create a directory with the given filenames."""
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _ms_names_and_types(
    sources: list,
) -> list[tuple[str, MediaSourceType]]:
    """Extract (name, type) pairs for easy assertion."""
    return [(ms.name, ms.media_source_type) for ms in sources]


# ---------------------------------------------------------------------------
# _is_std_source_dir
# ---------------------------------------------------------------------------


class TestIsStdSourceDir:
    def test_std_with_orig_img(self, tmp_path: Path) -> None:
        d = tmp_path / "std-nelu"
        _setup_dir(d / "orig-img", ["sunset.heic"])
        assert _is_std_source_dir(d) is True

    def test_std_with_orig_vid(self, tmp_path: Path) -> None:
        d = tmp_path / "std-nelu"
        _setup_dir(d / "orig-vid", ["clip.mov"])
        assert _is_std_source_dir(d) is True

    def test_std_without_orig_dirs(self, tmp_path: Path) -> None:
        d = tmp_path / "std-nelu"
        d.mkdir(parents=True)
        assert _is_std_source_dir(d) is False

    def test_not_std_prefix(self, tmp_path: Path) -> None:
        d = tmp_path / "nelu-img"
        _setup_dir(d / "orig-img", ["sunset.heic"])
        assert _is_std_source_dir(d) is False

    def test_file_not_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "std-nelu"
        f.write_text("not a dir")
        assert _is_std_source_dir(f) is False


# ---------------------------------------------------------------------------
# discover_media_sources — std detection
# ---------------------------------------------------------------------------


class TestDiscoverMediaSourcesStd:
    def test_detects_std_with_orig_img(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        ms = sources[0]
        assert ms.name == "nelu"
        assert ms.media_source_type == MediaSourceType.STD
        assert ms.archive_dir == "std-nelu"

    def test_detects_std_with_orig_vid(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        _setup_dir(tmp_path / "nelu-vid", ["clip.mov"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        assert sources[0].media_source_type == MediaSourceType.STD

    def test_detects_legacy_std_without_archive(self, tmp_path: Path) -> None:
        """Legacy std: browsable dirs exist but no std-{name}/ archive."""
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        ms = sources[0]
        assert ms.name == "nelu"
        assert ms.media_source_type == MediaSourceType.STD

    def test_legacy_std_from_vid(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "nelu-vid", ["clip.mov"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        assert sources[0].name == "nelu"

    def test_legacy_std_not_detected_when_ios_exists(self, tmp_path: Path) -> None:
        """If ios-{name}/ exists, browsable dirs are iOS, not legacy std."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        assert sources[0].media_source_type == MediaSourceType.IOS

    def test_legacy_std_not_detected_when_migrated_std_exists(
        self, tmp_path: Path
    ) -> None:
        """If std-{name}/ exists, browsable dirs are not also legacy std."""
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])

        sources = discover_media_sources(tmp_path)

        # Should be exactly one source, not two
        assert len(sources) == 1
        assert sources[0].name == "nelu"


# ---------------------------------------------------------------------------
# discover_media_sources — mixed albums
# ---------------------------------------------------------------------------


class TestDiscoverMediaSourcesMixed:
    def test_ios_plus_migrated_std_plus_legacy_std(self, tmp_path: Path) -> None:
        """Album with iOS main + migrated std (bruno) + legacy std (nelu)."""
        # iOS source: main
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC"])

        # Migrated std source: bruno
        _setup_dir(tmp_path / "std-bruno/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "bruno-img", ["sunset.heic"])

        # Legacy std source: nelu (no std-nelu/ archive)
        _setup_dir(tmp_path / "nelu-img", ["beach.png"])

        sources = discover_media_sources(tmp_path)

        names_types = _ms_names_and_types(sources)
        # main is first (sorted priority), then alphabetically
        assert ("main", MediaSourceType.IOS) in names_types
        assert ("bruno", MediaSourceType.STD) in names_types
        assert ("nelu", MediaSourceType.STD) in names_types
        assert len(sources) == 3

    def test_main_sorted_first(self, tmp_path: Path) -> None:
        """The 'main' media source always sorts first regardless of type."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "std-alice/orig-img", ["photo.heic"])
        _setup_dir(tmp_path / "alice-img", ["photo.heic"])

        sources = discover_media_sources(tmp_path)

        assert sources[0].name == "main"
        assert sources[1].name == "alice"

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert discover_media_sources(tmp_path) == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        assert discover_media_sources(tmp_path / "nonexistent") == []


# ---------------------------------------------------------------------------
# std_media_source factory
# ---------------------------------------------------------------------------


class TestStdMediaSource:
    def test_creates_correct_paths(self) -> None:
        ms = std_media_source("nelu")
        assert ms.name == "nelu"
        assert ms.media_source_type == MediaSourceType.STD
        assert ms.archive_dir == "std-nelu"
        assert ms.orig_img_dir == "std-nelu/orig-img"
        assert ms.edit_img_dir == "std-nelu/edit-img"
        assert ms.orig_vid_dir == "std-nelu/orig-vid"
        assert ms.edit_vid_dir == "std-nelu/edit-vid"
        assert ms.img_dir == "nelu-img"
        assert ms.vid_dir == "nelu-vid"
        assert ms.jpg_dir == "nelu-jpg"

    def test_is_std(self) -> None:
        ms = std_media_source("nelu")
        assert ms.is_std is True
        assert ms.is_ios is False

    def test_key_fn_uses_stem(self) -> None:
        ms = std_media_source("nelu")
        assert ms.key_fn("sunset.heic") == "sunset"
        assert ms.key_fn("beach.png") == "beach"
