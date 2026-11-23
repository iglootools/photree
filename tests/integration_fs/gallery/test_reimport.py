from pathlib import Path

import pytest

from photree.album.jpeg import noop_convert_single
from photree.album.refresh import AlbumRefreshResult
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import load_album_metadata
from photree.gallery.importer import (
    TargetExistsError,
    compute_target_dir,
    import_album,
    reimport_album,
    swap_into_place,
)
from tests.testkit import make_gallery, write_file


def _album_id(album_dir: Path) -> str:
    metadata = load_album_metadata(album_dir)
    assert metadata is not None
    return metadata.id


def _setup_ios_album(album: Path) -> None:
    write_file(album / "ios-main/orig-img/IMG_0001.HEIC", "heic-data")
    write_file(album / "main-img/IMG_0001.HEIC", "heic-data")
    write_file(album / "main-jpg/IMG_0001.jpg", "jpg-data")
    (album / "ios-main/orig-vid").mkdir(parents=True, exist_ok=True)
    (album / "main-vid").mkdir(parents=True, exist_ok=True)


def _uuid_for_key(target: Path, key: str) -> str | None:
    media = load_media_metadata(target)
    assert media is not None
    images = media.media_sources["main"].images
    return next((uuid for uuid, k in images.items() if k == key), None)


def _first_import(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Import a minimal album. Returns (gallery, source, target)."""
    gallery = make_gallery(tmp_path)
    source = tmp_path / "2024-07-14 - Hiking"
    _setup_ios_album(source)
    result = import_album(
        source_dir=source,
        gallery_dir=gallery,
        convert_file=noop_convert_single,
    )
    return gallery, source, result.target_dir


class _RefreshFailedError(Exception):
    pass


def _failing_refresh(*_args: object, **_kwargs: object) -> AlbumRefreshResult:
    raise _RefreshFailedError


class TestReimportAlbum:
    def test_preserves_id_and_existing_uuids(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        original_id = _album_id(target)
        uuid_0001 = _uuid_for_key(target, "0001")

        write_file(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")
        write_file(source / "main-img/IMG_0002.HEIC", "heic2")

        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        meta = load_album_metadata(target)
        assert meta is not None
        assert meta.id == original_id
        # Existing key keeps its UUID; new key gets one.
        assert _uuid_for_key(target, "0001") == uuid_0001
        assert _uuid_for_key(target, "0002") is not None
        assert (target / "ios-main/orig-img/IMG_0002.HEIC").is_file()

    def test_prunes_removed_files(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        write_file(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")
        write_file(source / "main-img/IMG_0002.HEIC", "heic2")
        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )
        uuid_0001 = _uuid_for_key(target, "0001")

        (source / "ios-main/orig-img/IMG_0002.HEIC").unlink()
        (source / "main-img/IMG_0002.HEIC").unlink()
        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        assert _uuid_for_key(target, "0002") is None
        assert _uuid_for_key(target, "0001") == uuid_0001
        assert not (target / "ios-main/orig-img/IMG_0002.HEIC").exists()

    def test_drops_stale_browsable_files(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        # Add a file directly to the gallery copy that is absent from source.
        write_file(target / "ios-main/orig-img/IMG_0099.HEIC", "stale")
        write_file(target / "main-img/IMG_0099.HEIC", "stale")

        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        # Reimport mirrors the source, so the stale gallery-only file is gone.
        assert not (target / "ios-main/orig-img/IMG_0099.HEIC").exists()
        assert (target / "ios-main/orig-img/IMG_0001.HEIC").is_file()

    def test_atomic_on_refresh_failure(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        original_id = _album_id(target)
        write_file(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")

        with pytest.raises(_RefreshFailedError):
            reimport_album(
                source_dir=source,
                gallery_dir=gallery,
                existing_dir=target,
                convert_file=noop_convert_single,
                refresh=_failing_refresh,
            )

        meta = load_album_metadata(target)
        assert meta is not None
        assert meta.id == original_id
        assert (target / "ios-main/orig-img/IMG_0001.HEIC").is_file()
        assert not (target.parent / ".2024-07-14 - Hiking.reimport").exists()
        assert not (target.parent / ".2024-07-14 - Hiking.old").exists()

    def test_dry_run_mutates_nothing(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        write_file(source / "ios-main/orig-img/IMG_0002.HEIC", "heic2")

        reimport_album(
            source_dir=source,
            gallery_dir=gallery,
            existing_dir=target,
            dry_run=True,
            convert_file=noop_convert_single,
        )

        assert not (target / "ios-main/orig-img/IMG_0002.HEIC").exists()

    def test_rename_moves_album_and_keeps_id(self, tmp_path: Path) -> None:
        gallery, source, target = _first_import(tmp_path)
        original_id = _album_id(target)

        # The source is renamed (same date, new title) but is the same album.
        renamed = source.parent / "2024-07-14 - Hiking the Rockies"
        source.rename(renamed)
        new_target = compute_target_dir(gallery, renamed.name)

        reimport_album(
            source_dir=renamed,
            gallery_dir=gallery,
            existing_dir=target,
            convert_file=noop_convert_single,
        )

        assert not target.exists()
        assert new_target.is_dir()
        meta = load_album_metadata(new_target)
        assert meta is not None
        assert meta.id == original_id

    def test_rename_onto_occupied_name_is_refused(self, tmp_path: Path) -> None:
        """Regression: the live album was moved aside, then the swap failed."""
        gallery, source, target = _first_import(tmp_path)
        occupied = compute_target_dir(gallery, "2024-07-14 - Hiking the Rockies")
        write_file(occupied / "ios-main/orig-img/IMG_0009.HEIC", "other album")
        renamed = source.parent / occupied.name
        source.rename(renamed)

        with pytest.raises(TargetExistsError) as exc_info:
            reimport_album(
                source_dir=renamed,
                gallery_dir=gallery,
                existing_dir=target,
                convert_file=noop_convert_single,
            )

        assert exc_info.value.target == occupied
        assert (target / "ios-main/orig-img/IMG_0001.HEIC").is_file()
        assert (occupied / "ios-main/orig-img/IMG_0009.HEIC").is_file()


class TestSwapIntoPlace:
    def test_restores_live_album_when_final_rename_fails(self, tmp_path: Path) -> None:
        existing = tmp_path / "albums" / "2024" / "2024-07-14 - Hiking"
        write_file(existing / "live.txt", "live")
        staging = tmp_path / "albums" / "2024" / ".2024-07-14 - Hiking.reimport"
        write_file(staging / "new.txt", "new")
        # A non-empty directory at the target makes the final rename fail.
        target = tmp_path / "albums" / "2024" / "2024-07-14 - Renamed"
        write_file(target / "occupant.txt", "occupant")

        with pytest.raises(OSError):  # noqa: PT011 - rename's own error; errno and text vary by OS
            swap_into_place(existing, staging, target)

        assert (existing / "live.txt").read_text(encoding="utf-8") == "live"
        assert not (target.parent / ".2024-07-14 - Renamed.old").exists()
