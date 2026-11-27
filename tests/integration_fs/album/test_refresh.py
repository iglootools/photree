from pathlib import Path

from photree.album.check.media_metadata import check_media_metadata
from photree.album.id import generate_album_id
from photree.album.refresh import refresh_album_derived_data, refresh_media_metadata
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.foundation.linking import LinkMode
from tests.fakes import FakeExifTool
from tests.testkit import file_names, mark_album, write_file


def _setup_ios_album(album_dir: Path) -> None:
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    write_file(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
    write_file(album_dir / "ios-main" / "orig-img" / "IMG_0411.HEIC")
    write_file(album_dir / "ios-main" / "orig-vid" / "IMG_0115.MOV")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


def _setup_std_album(album_dir: Path, name: str = "nelu") -> None:
    write_file(album_dir / f"std-{name}" / "orig-img" / "DSC_1234.JPG")
    write_file(album_dir / f"std-{name}" / "orig-img" / "DSC_5678.JPG")
    write_file(album_dir / f"std-{name}" / "orig-vid" / "VID_001.MOV")
    (album_dir / f"{name}-img").mkdir(parents=True, exist_ok=True)
    (album_dir / f"{name}-jpg").mkdir(parents=True, exist_ok=True)


class TestRefreshFreshAlbum:
    def test_assigns_ids_to_all_media(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = refresh_media_metadata(album)

        assert len(result.by_media_source) == 1
        ms_name, ms_result = result.by_media_source[0]
        assert ms_name == "main"
        assert ms_result.new_images == 2
        assert ms_result.new_videos == 1
        assert ms_result.removed_images == 0
        assert ms_result.removed_videos == 0

    def test_creates_media_yaml(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        meta = load_media_metadata(album)
        assert meta is not None
        assert len(meta.media_sources["main"].images) == 2
        assert len(meta.media_sources["main"].videos) == 1

    def test_image_keys_are_image_numbers(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        meta = load_media_metadata(album)
        assert meta is not None
        keys = set(meta.media_sources["main"].images.values())
        assert keys == {"0410", "0411"}

    def test_video_keys_are_image_numbers(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        meta = load_media_metadata(album)
        assert meta is not None
        keys = set(meta.media_sources["main"].videos.values())
        assert keys == {"0115"}


class TestRefreshIdempotent:
    def test_no_changes_on_second_run(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)
        meta_before = load_media_metadata(album)

        result = refresh_media_metadata(album)

        meta_after = load_media_metadata(album)
        assert meta_before == meta_after
        _, ms_result = result.by_media_source[0]
        assert ms_result.new_images == 0
        assert ms_result.new_videos == 0
        assert ms_result.removed_images == 0
        assert ms_result.removed_videos == 0
        assert not result.changed

    def test_preserves_existing_uuids(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)
        meta_before = load_media_metadata(album)
        assert meta_before is not None
        uuids_before = set(meta_before.media_sources["main"].images.keys())

        refresh_media_metadata(album)
        meta_after = load_media_metadata(album)
        assert meta_after is not None
        uuids_after = set(meta_after.media_sources["main"].images.keys())

        assert uuids_before == uuids_after


class TestRefreshNewFiles:
    def test_assigns_ids_to_new_files_only(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)
        meta_before = load_media_metadata(album)
        assert meta_before is not None
        uuids_before = set(meta_before.media_sources["main"].images.keys())

        write_file(album / "ios-main" / "orig-img" / "IMG_0412.HEIC")

        result = refresh_media_metadata(album)
        _, ms_result = result.by_media_source[0]
        assert ms_result.new_images == 1
        assert ms_result.removed_images == 0

        meta_after = load_media_metadata(album)
        assert meta_after is not None
        uuids_after = set(meta_after.media_sources["main"].images.keys())
        assert uuids_before < uuids_after  # subset — all old IDs preserved
        assert len(uuids_after) == 3


class TestRefreshRemovedFiles:
    def test_removes_stale_entries(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        (album / "ios-main" / "orig-img" / "IMG_0410.HEIC").unlink()

        result = refresh_media_metadata(album)
        _, ms_result = result.by_media_source[0]
        assert ms_result.removed_images == 1
        assert ms_result.new_images == 0

        meta = load_media_metadata(album)
        assert meta is not None
        assert len(meta.media_sources["main"].images) == 1
        keys = set(meta.media_sources["main"].images.values())
        assert keys == {"0411"}


class TestRefreshMixed:
    def test_add_and_remove(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        (album / "ios-main" / "orig-img" / "IMG_0410.HEIC").unlink()
        write_file(album / "ios-main" / "orig-img" / "IMG_0999.HEIC")

        result = refresh_media_metadata(album)
        _, ms_result = result.by_media_source[0]
        assert ms_result.new_images == 1
        assert ms_result.removed_images == 1
        assert result.changed


class TestRefreshDryRun:
    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = refresh_media_metadata(album, dry_run=True)

        assert result.total_new == 3
        assert load_media_metadata(album) is None


class TestRefreshMultipleSources:
    def test_ios_and_std(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        _setup_std_album(album, "nelu")

        result = refresh_media_metadata(album)

        assert len(result.by_media_source) == 2
        names = {name for name, _ in result.by_media_source}
        assert names == {"main", "nelu"}

        meta = load_media_metadata(album)
        assert meta is not None
        assert len(meta.media_sources["main"].images) == 2
        assert len(meta.media_sources["nelu"].images) == 2

        # Std source keys are stems
        std_keys = set(meta.media_sources["nelu"].images.values())
        assert std_keys == {"DSC_1234", "DSC_5678"}


def _snapshot(album: Path) -> dict[str, tuple[str, float]]:
    """Return every file under *album* with its content and mtime."""
    return {
        str(f.relative_to(album)): (f.read_text(encoding="utf-8"), f.stat().st_mtime)
        for f in album.rglob("*")
        if f.is_file()
    }


class TestRefreshDerivedDataDryRun:
    def test_dry_run_leaves_every_derived_file_alone(self, tmp_path: Path) -> None:
        # Every step has work to do: a Live Photo missing from main-img/, a
        # JPEG dir with a stale file, no media IDs and no EXIF cache, which
        # the std source, with no browsable files to read, would only create.
        album = tmp_path / "album"
        write_file(album / "std-nelu" / "orig-img" / "DSC_0001.JPG")
        write_file(album / "ios-main" / "orig-img" / "IMG_0001.JPG")
        write_file(album / "ios-main" / "orig-img" / "IMG_0002.JPG")
        write_file(album / "ios-main" / "orig-img" / "IMG_0002.MOV")
        write_file(album / "main-img" / "IMG_0001.JPG")
        write_file(album / "main-jpg" / "IMG_0001.JPG")
        write_file(album / "main-jpg" / "IMG_9999.JPG")
        mark_album(album)
        before = _snapshot(album)

        refresh_album_derived_data(
            album,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
            dry_run=True,
        )

        assert _snapshot(album) == before
        assert not (album / "main-vid").exists()


class TestRefreshDerivedDataJpeg:
    def test_forced_browsable_refresh_regenerates_jpegs_of_changed_images(
        self,
        tmp_path: Path,
    ) -> None:
        # The JPEG dir's own gate only checks names, so an image whose content
        # changed under the same name (an EXIF fix on the archive) must be
        # regenerated because its browsable img dir was rebuilt.
        album = tmp_path / "album"
        write_file(album / "std-main" / "orig-img" / "DSC_0001.JPG", "before")
        refresh_album_derived_data(
            album,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
        )
        write_file(album / "std-main" / "orig-img" / "DSC_0001.JPG", "after")

        refresh_album_derived_data(
            album,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
            force_browsable=True,
        )

        jpeg = album / "main-jpg" / "DSC_0001.JPG"
        assert jpeg.read_text(encoding="utf-8") == "after"


class TestRefreshVideoExtensions:
    def test_ios_source_leaves_an_mp4_out(self, tmp_path: Path) -> None:
        # An iPhone records only .mov: an .mp4 in an iOS archive is not one of
        # its media items, gets no ID and is not linked into main-vid/.
        album = tmp_path / "album"
        write_file(album / "ios-main" / "orig-img" / "IMG_0001.JPG")
        write_file(album / "ios-main" / "orig-vid" / "IMG_0115.MOV")
        write_file(album / "ios-main" / "orig-vid" / "IMG_0116.MP4")

        refresh_album_derived_data(
            album,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
        )

        meta = load_media_metadata(album)
        assert meta is not None
        assert set(meta.media_sources["main"].videos.values()) == {"0115"}
        assert file_names(album / "main-vid") == {"IMG_0115.MOV"}
        sources = discover_media_sources(album)
        assert check_media_metadata(album, media_sources=sources).in_sync

    def test_std_source_keeps_an_mp4(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        write_file(album / "std-main" / "orig-img" / "DSC_0001.JPG")
        write_file(album / "std-main" / "orig-vid" / "VID_001.MOV")
        write_file(album / "std-main" / "orig-vid" / "VID_002.MP4")

        refresh_album_derived_data(
            album,
            link_mode=LinkMode.COPY,
            exiftool=FakeExifTool({}),
        )

        meta = load_media_metadata(album)
        assert meta is not None
        videos = set(meta.media_sources["main"].videos.values())
        assert videos == {"VID_001", "VID_002"}
        assert file_names(album / "main-vid") == {"VID_001.MOV", "VID_002.MP4"}


def test_media_ids_use_injected_generator(tmp_path: Path) -> None:
    write_file(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
    write_file(tmp_path / "ios-main/orig-vid/IMG_0002.MOV")
    ids = iter(["id-image", "id-video"])

    refresh_media_metadata(tmp_path, new_id=lambda: next(ids))

    meta = load_media_metadata(tmp_path)
    assert meta is not None
    assert meta.media_sources["main"].images == {"id-image": "0001"}
    assert meta.media_sources["main"].videos == {"id-video": "0002"}
