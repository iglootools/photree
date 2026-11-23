from pathlib import Path

import pytest

from photree.album.check import run_album_check
from photree.album.check.output.album import format_album_preflight_checks
from photree.album.store.album_discovery import has_media_sources
from photree.album.store.media_source import (
    MediaSource,
    MediaSourceType,
    std_media_source,
)
from photree.album.store.media_sources_discovery import (
    MediaSourceConflictError,
    discover_media_sources,
    find_media_source_conflicts,
    is_std_source_dir,
)
from photree.albums.cmd_handler.check import batch_check
from photree.foundation.linking import LinkMode
from tests.testkit import write_file, write_files


def _ms_names_and_types(
    sources: list[MediaSource],
) -> list[tuple[str, MediaSourceType]]:
    """Extract (name, type) pairs for easy assertion."""
    return [(ms.name, ms.media_source_type) for ms in sources]


class TestIsStdSourceDir:
    def test_std_with_orig_img(self, tmp_path: Path) -> None:
        d = tmp_path / "std-nelu"
        write_files(d / "orig-img", ["sunset.heic"])
        assert is_std_source_dir(d) is True

    def test_std_with_orig_vid(self, tmp_path: Path) -> None:
        d = tmp_path / "std-nelu"
        write_files(d / "orig-vid", ["clip.mov"])
        assert is_std_source_dir(d) is True

    def test_std_without_orig_dirs(self, tmp_path: Path) -> None:
        d = tmp_path / "std-nelu"
        d.mkdir(parents=True)
        assert is_std_source_dir(d) is False

    def test_not_std_prefix(self, tmp_path: Path) -> None:
        d = tmp_path / "nelu-img"
        write_files(d / "orig-img", ["sunset.heic"])
        assert is_std_source_dir(d) is False

    def test_file_not_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "std-nelu"
        f.write_text("not a dir")
        assert is_std_source_dir(f) is False


class TestDiscoverMediaSourcesStd:
    def test_detects_std_with_orig_img(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-img", ["sunset.heic"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        ms = sources[0]
        assert ms.name == "nelu"
        assert ms.media_source_type == MediaSourceType.STD
        assert ms.archive_dir == "std-nelu"

    def test_detects_std_with_orig_vid(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        write_files(tmp_path / "nelu-vid", ["clip.mov"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        assert sources[0].media_source_type == MediaSourceType.STD

    def test_browsable_only_dir_is_not_a_media_source(self, tmp_path: Path) -> None:
        """Browsable dirs without a backing archive are not media sources."""
        write_files(tmp_path / "nelu-img", ["sunset.heic"])

        assert discover_media_sources(tmp_path) == []

    def test_browsable_only_vid_dir_is_not_a_media_source(self, tmp_path: Path) -> None:
        write_files(tmp_path / "nelu-vid", ["clip.mov"])

        assert discover_media_sources(tmp_path) == []

    def test_browsable_dirs_alongside_ios_archive(self, tmp_path: Path) -> None:
        """An ios-{name}/ archive plus its browsable dirs is one iOS source."""
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        assert sources[0].media_source_type == MediaSourceType.IOS

    def test_browsable_dirs_alongside_std_archive(self, tmp_path: Path) -> None:
        """A std-{name}/ archive plus its browsable dirs is one std source."""
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-img", ["sunset.heic"])

        sources = discover_media_sources(tmp_path)

        assert len(sources) == 1
        assert sources[0].name == "nelu"


class TestDiscoverMediaSourcesMixed:
    def test_ios_plus_std_sources(self, tmp_path: Path) -> None:
        """Album with iOS main + std (bruno); browsable-only dirs are ignored."""
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC"])

        write_files(tmp_path / "std-bruno/orig-img", ["sunset.heic"])
        write_files(tmp_path / "bruno-img", ["sunset.heic"])

        # Browsable-only dirs without an archive: not a media source
        write_files(tmp_path / "nelu-img", ["beach.png"])

        sources = discover_media_sources(tmp_path)

        names_types = _ms_names_and_types(sources)
        assert ("main", MediaSourceType.IOS) in names_types
        assert ("bruno", MediaSourceType.STD) in names_types
        assert "nelu" not in {ms.name for ms in sources}
        assert len(sources) == 2

    def test_main_sorted_first(self, tmp_path: Path) -> None:
        """The 'main' media source always sorts first regardless of type."""
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "std-alice/orig-img", ["photo.heic"])
        write_files(tmp_path / "alice-img", ["photo.heic"])

        sources = discover_media_sources(tmp_path)

        assert sources[0].name == "main"
        assert sources[1].name == "alice"

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert discover_media_sources(tmp_path) == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        assert discover_media_sources(tmp_path / "nonexistent") == []


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


class TestMediaSourceConflicts:
    def test_ios_and_std_with_same_name_conflict(self, tmp_path: Path) -> None:
        write_file(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(tmp_path / "std-main/orig-img/DSC_0001.JPG")
        write_file(tmp_path / "std-nelu/orig-img/DSC_0002.JPG")

        assert find_media_source_conflicts(tmp_path) == ("main",)
        with pytest.raises(MediaSourceConflictError) as exc_info:
            discover_media_sources(tmp_path)
        assert exc_info.value.names == ("main",)
        assert exc_info.value.album_dir == tmp_path

    def test_discovery_still_finds_conflicted_album(self, tmp_path: Path) -> None:
        """Album discovery must not crash a whole batch on one bad album."""
        write_file(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(tmp_path / "std-main/orig-img/DSC_0001.JPG")

        assert has_media_sources(tmp_path)

    def test_check_reports_conflict_instead_of_raising(self, tmp_path: Path) -> None:
        """A batch check must keep going: the clash is a failed check."""
        album = tmp_path / "2024-07-14 - Trip"
        write_file(album / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(album / "std-main/orig-img/DSC_0001.JPG")

        result = run_album_check(
            album,
            sips_available=True,
            exiftool=None,
            link_mode=LinkMode.HARDLINK,
        )

        assert result.media_source_conflicts == ("main",)
        assert not result.success
        assert "media source conflict" in result.error_labels
        assert result.naming is not None
        assert result.naming.success
        assert "ios-<name>/ and std-<name>/ both present for: main" in (
            format_album_preflight_checks(result)
        )

    def test_batch_check_continues_past_conflict(self, tmp_path: Path) -> None:
        conflicted = tmp_path / "2024-07-14 - Trip"
        write_file(conflicted / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(conflicted / "std-main/orig-img/DSC_0001.JPG")
        healthy = tmp_path / "2024-07-15 - Next"
        write_file(healthy / "ios-main/orig-img/IMG_0002.HEIC")
        ends: list[tuple[str, bool, tuple[str, ...], tuple[str, ...]]] = []

        def record_end(
            name: str,
            *,
            success: bool,
            error_labels: tuple[str, ...],
            warning_labels: tuple[str, ...],
        ) -> None:
            ends.append((name, success, error_labels, warning_labels))

        batch_check(
            [conflicted, healthy],
            sips_available=True,
            link_mode_for=lambda _: LinkMode.HARDLINK,
            check_naming=False,
            on_end=record_end,
        )

        assert len(ends) == 2
        assert ends[0][:2] == (conflicted.name, False)
        assert "media source conflict" in ends[0][2]

    def test_distinct_names_do_not_conflict(self, tmp_path: Path) -> None:
        write_file(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        write_file(tmp_path / "std-nelu/orig-img/DSC_0001.JPG")

        assert find_media_source_conflicts(tmp_path) == ()
        assert [ms.name for ms in discover_media_sources(tmp_path)] == ["main", "nelu"]
