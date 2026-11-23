from pathlib import Path

import pytest

from photree.album.cli.media_op_output import (
    format_media_op_error,
    format_media_op_summary,
)
from photree.album.media import (
    MediaOpError,
    MediaOpErrorKind,
    move_media,
    resolve_variants,
    rm_media,
)
from photree.album.refresh import refresh_media_metadata
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
    save_media_metadata,
)
from photree.foundation.metadata_io import InvalidMetadataError
from tests.testkit import file_names, mark_album, write_files

PHOTREE_DIR = ".photree"


def _image_ids(album: Path) -> dict[str, str]:
    metadata = load_media_metadata(album)
    assert metadata is not None
    return dict(metadata.media_sources["main"].images)


def _setup_ios_album(album: Path) -> None:
    """Create an iOS album with one image (0410) in orig, edit, main and jpg."""
    write_files(album / PHOTREE_DIR, [])
    mark_album(album)
    write_files(
        album / "ios-main/orig-img",
        ["IMG_0410.HEIC", "IMG_0410.AAE"],
    )
    write_files(
        album / "ios-main/edit-img",
        ["IMG_E0410.HEIC", "IMG_O0410.AAE"],
    )
    write_files(album / "main-img", ["IMG_E0410.HEIC"])
    write_files(album / "main-jpg", ["IMG_E0410.jpg"])


def _setup_ios_album_with_video(album: Path) -> None:
    """Create a minimal iOS album with one video (0115)."""
    write_files(album / PHOTREE_DIR, [])
    mark_album(album)
    write_files(album / "ios-main/orig-img", [])
    write_files(album / "ios-main/orig-vid", ["IMG_0115.MOV"])
    write_files(album / "ios-main/edit-vid", ["IMG_E0115.MOV"])
    write_files(album / "main-vid", ["IMG_E0115.MOV"])


def _setup_ios_album_with_live_photo(album: Path) -> None:
    """Create an iOS album with one Live Photo (0001): a still and its MOV."""
    write_files(album / PHOTREE_DIR, [])
    mark_album(album)
    write_files(album / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.MOV"])
    write_files(album / "main-img", ["IMG_0001.HEIC", "IMG_0001.MOV"])
    write_files(album / "main-jpg", ["IMG_0001.jpg"])


def _setup_std_album(album: Path, media_source_name: str = "nelu") -> None:
    """Create a minimal std contributor album (archive + browsable dirs)."""
    write_files(album / PHOTREE_DIR, [])
    mark_album(album)
    write_files(
        album / f"std-{media_source_name}/orig-img",
        ["sunset.heic", "beach.png"],
    )
    write_files(album / f"{media_source_name}-img", ["sunset.heic", "beach.png"])
    write_files(album / f"{media_source_name}-jpg", ["sunset.jpg", "beach.png"])


class TestResolveVariants:
    def test_ios_image_resolves_all_dirs(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = resolve_variants(album, ["main-jpg/IMG_E0410.jpg"])

        dirs_found = {subdir for subdir, _ in result}
        assert "ios-main/orig-img" in dirs_found
        assert "ios-main/edit-img" in dirs_found
        assert "main-img" in dirs_found
        assert "main-jpg" in dirs_found

    def test_ios_image_finds_all_variants_by_number(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = resolve_variants(album, ["main-jpg/IMG_E0410.jpg"])

        all_files = {f for _, files in result for f in files}
        assert "IMG_0410.HEIC" in all_files
        assert "IMG_0410.AAE" in all_files
        assert "IMG_E0410.HEIC" in all_files
        assert "IMG_O0410.AAE" in all_files
        assert "IMG_E0410.jpg" in all_files

    def test_ios_any_variant_resolves_same(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        from_jpg = resolve_variants(album, ["main-jpg/IMG_E0410.jpg"])
        from_orig = resolve_variants(album, ["ios-main/orig-img/IMG_0410.HEIC"])
        from_edit = resolve_variants(album, ["ios-main/edit-img/IMG_E0410.HEIC"])

        def _all_files(r: list[tuple[str, list[str]]]) -> set[str]:
            return {f for _, files in r for f in files}

        assert _all_files(from_jpg) == _all_files(from_orig) == _all_files(from_edit)

    def test_ios_video_resolves_video_dirs(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album_with_video(album)

        result = resolve_variants(album, ["main-vid/IMG_E0115.MOV"])

        dirs_found = {subdir for subdir, _ in result}
        assert "ios-main/orig-vid" in dirs_found
        assert "ios-main/edit-vid" in dirs_found
        assert "main-vid" in dirs_found

    def test_live_photo_mov_resolves_its_image(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album_with_live_photo(album)

        result = resolve_variants(album, ["main-img/IMG_0001.MOV"])

        assert dict(result) == {
            "ios-main/orig-img": ["IMG_0001.HEIC", "IMG_0001.MOV"],
            "main-img": ["IMG_0001.HEIC", "IMG_0001.MOV"],
            "main-jpg": ["IMG_0001.jpg"],
        }

    def test_plain_image_resolves_by_stem(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_album(album)

        result = resolve_variants(album, ["nelu-img/sunset.heic"])

        dirs_found = {subdir for subdir, _ in result}
        assert "nelu-img" in dirs_found
        assert "nelu-jpg" in dirs_found
        # jpg dir should have sunset.jpg matched by stem
        jpg_files = next(files for d, files in result if d == "nelu-jpg")
        assert "sunset.jpg" in jpg_files

    def test_missing_dir_skipped(self, tmp_path: Path) -> None:
        """Directories that don't exist on disk are silently skipped."""
        album = tmp_path / "album"
        write_files(album / PHOTREE_DIR, [])
        mark_album(album)
        write_files(album / "ios-main/orig-img", ["IMG_0410.HEIC"])
        write_files(album / "main-img", ["IMG_0410.HEIC"])
        write_files(album / "main-jpg", ["IMG_0410.jpg"])
        # No edit-img dir

        result = resolve_variants(album, ["main-jpg/IMG_0410.jpg"])

        dirs_found = {subdir for subdir, _ in result}
        assert "ios-main/edit-img" not in dirs_found

    def test_invalid_path_raises(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        with pytest.raises(MediaOpError) as exc_info:
            resolve_variants(album, ["unknown-dir/IMG_0410.jpg"])
        assert exc_info.value.kind == MediaOpErrorKind.UNKNOWN_DIRECTORY
        assert exc_info.value.subdir == "unknown-dir"

    def test_no_directory_in_path_raises(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        with pytest.raises(MediaOpError) as exc_info:
            resolve_variants(album, ["IMG_0410.jpg"])
        assert exc_info.value.kind == MediaOpErrorKind.PATH_WITHOUT_DIRECTORY
        assert exc_info.value.rel_path == "IMG_0410.jpg"

    def test_no_media_sources_raises(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()

        with pytest.raises(MediaOpError) as exc_info:
            resolve_variants(album, ["main-jpg/IMG_0410.jpg"])
        assert exc_info.value.kind == MediaOpErrorKind.NO_MEDIA_SOURCES

    def test_error_message_uses_display_path(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()

        with pytest.raises(MediaOpError) as exc_info:
            resolve_variants(album, ["main-jpg/IMG_0410.jpg"])
        message = format_media_op_error(exc_info.value, tmp_path)
        assert str(tmp_path) not in message
        assert "album" in message

    def test_multiple_numbers(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        write_files(album / PHOTREE_DIR, [])
        mark_album(album)
        write_files(
            album / "ios-main/orig-img",
            ["IMG_0410.HEIC", "IMG_0411.HEIC"],
        )
        write_files(album / "main-img", ["IMG_0410.HEIC", "IMG_0411.HEIC"])
        write_files(album / "main-jpg", ["IMG_0410.jpg", "IMG_0411.jpg"])

        result = resolve_variants(
            album,
            ["main-jpg/IMG_0410.jpg", "main-jpg/IMG_0411.jpg"],
        )

        all_files = {f for _, files in result for f in files}
        assert "IMG_0410.HEIC" in all_files
        assert "IMG_0411.HEIC" in all_files
        assert "IMG_0410.jpg" in all_files
        assert "IMG_0411.jpg" in all_files


class TestMoveMedia:
    def test_ios_moves_all_variants(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        result = move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        assert result.total > 0
        # Source dirs should be removed (empty after move)
        assert not (src / "ios-main/orig-img").exists()
        assert not (src / "ios-main/edit-img").exists()
        assert not (src / "ios-main").exists()
        assert not (src / "main-img").exists()
        assert not (src / "main-jpg").exists()
        assert "IMG_0410.HEIC" in file_names(dst / "ios-main/orig-img")
        assert "IMG_E0410.HEIC" in file_names(dst / "ios-main/edit-img")
        assert "IMG_E0410.HEIC" in file_names(dst / "main-img")
        assert "IMG_E0410.jpg" in file_names(dst / "main-jpg")

    def test_ios_video_moves_all_variants(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album_with_video(src)
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        result = move_media(src, dst, ["main-vid/IMG_E0115.MOV"])

        assert result.total > 0
        assert file_names(src / "main-vid") == set()
        assert "IMG_E0115.MOV" in file_names(dst / "main-vid")
        assert "IMG_0115.MOV" in file_names(dst / "ios-main/orig-vid")

    def test_plain_moves_by_stem(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_std_album(src)
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        result = move_media(src, dst, ["nelu-img/sunset.heic"])

        assert result.total > 0
        assert "sunset.heic" not in file_names(src / "nelu-img")
        assert "sunset.heic" in file_names(dst / "nelu-img")
        assert "sunset.jpg" in file_names(dst / "nelu-jpg")
        assert "beach.png" in file_names(src / "nelu-img")

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        result = move_media(src, dst, ["main-jpg/IMG_E0410.jpg"], dry_run=True)

        assert result.total > 0
        assert "IMG_0410.HEIC" in file_names(src / "ios-main/orig-img")
        assert "IMG_E0410.jpg" in file_names(src / "main-jpg")
        assert not (dst / "main-jpg").is_dir()

    def test_creates_dest_directories(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        dst.mkdir()

        move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        assert (dst / "ios-main/orig-img").is_dir()
        assert (dst / "main-jpg").is_dir()

    def test_keeps_dirs_with_remaining_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        write_files(src / PHOTREE_DIR, [])
        mark_album(src)
        write_files(
            src / "ios-main/orig-img",
            ["IMG_0410.HEIC", "IMG_0411.HEIC"],
        )
        write_files(src / "main-img", ["IMG_0410.HEIC", "IMG_0411.HEIC"])
        write_files(src / "main-jpg", ["IMG_0410.jpg", "IMG_0411.jpg"])
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        move_media(src, dst, ["main-jpg/IMG_0410.jpg"])

        # Dirs should still exist because IMG_0411 remains
        assert (src / "ios-main/orig-img").is_dir()
        assert (src / "main-img").is_dir()
        assert (src / "main-jpg").is_dir()
        assert "IMG_0411.HEIC" in file_names(src / "ios-main/orig-img")

    def test_refuses_to_overwrite_existing_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        _setup_ios_album(dst)

        with pytest.raises(MediaOpError) as exc_info:
            move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])
        assert exc_info.value.kind == MediaOpErrorKind.MOVE_CONFLICT
        assert "main-jpg/IMG_E0410.jpg" in exc_info.value.conflicts

        assert "IMG_0410.HEIC" in file_names(src / "ios-main/orig-img")

    def test_refuses_on_same_number_different_extension(self, tmp_path: Path) -> None:
        """Detects collision even when the exact filename doesn't match."""
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        write_files(src / PHOTREE_DIR, [])
        mark_album(src)
        write_files(src / "ios-main/orig-img", ["IMG_0410.HEIC"])
        write_files(src / "main-img", ["IMG_0410.HEIC"])
        write_files(src / "main-jpg", ["IMG_0410.jpg"])

        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)
        # Different extension, same number
        write_files(dst / "ios-main/orig-img", ["IMG_0410.JPG"])
        write_files(dst / "main-img", ["IMG_0410.JPG"])

        with pytest.raises(MediaOpError) as exc_info:
            move_media(src, dst, ["main-jpg/IMG_0410.jpg"])
        assert exc_info.value.kind == MediaOpErrorKind.MOVE_CONFLICT
        assert "ios-main/orig-img/IMG_0410.JPG" in exc_info.value.conflicts

    def test_refuses_when_dest_has_same_named_source_of_other_type(
        self,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        _setup_std_album(dst, media_source_name="main")

        with pytest.raises(MediaOpError) as exc_info:
            move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])
        assert exc_info.value.kind == MediaOpErrorKind.MEDIA_SOURCE_TYPE_MISMATCH
        assert exc_info.value.media_sources == ("main",)

        assert "IMG_0410.HEIC" in file_names(src / "ios-main/orig-img")
        assert not (dst / "ios-main").exists()

    def test_moves_into_dest_whose_other_sources_differ_in_type(
        self,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        _setup_std_album(dst, media_source_name="nelu")

        move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        assert "IMG_0410.HEIC" in file_names(dst / "ios-main/orig-img")

    def test_carries_media_ids_to_dest(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        write_files(src / "ios-main/orig-img", ["IMG_0411.HEIC"])
        save_media_metadata(
            src,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(
                        images={"id-0410": "0410", "id-0411": "0411"},
                    ),
                },
            ),
        )
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        assert _image_ids(src) == {"id-0411": "0411"}
        assert _image_ids(dst) == {"id-0410": "0410"}

    def test_moved_media_keeps_its_id_through_refresh(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        refresh_media_metadata(src)
        [media_id] = _image_ids(src)
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])
        refresh_media_metadata(dst)

        assert _image_ids(dst) == {media_id: "0410"}

    def test_dry_run_leaves_media_ids(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        refresh_media_metadata(src)
        ids_before = _image_ids(src)
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        move_media(src, dst, ["main-jpg/IMG_E0410.jpg"], dry_run=True)

        assert _image_ids(src) == ids_before
        assert load_media_metadata(dst) is None

    def test_refuses_before_moving_when_media_ids_are_unreadable(
        self,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        write_files(src / PHOTREE_DIR / "media-ids", [])
        (src / PHOTREE_DIR / "media-ids/main.yaml").write_text(
            "images: [",
            encoding="utf-8",
        )
        write_files(dst / PHOTREE_DIR, [])
        mark_album(dst)

        with pytest.raises(InvalidMetadataError):
            move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])
        assert "IMG_0410.HEIC" in file_names(src / "ios-main/orig-img")


class TestRmMedia:
    def test_ios_removes_all_variants(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = rm_media(album, ["main-jpg/IMG_E0410.jpg"])

        assert result.total > 0
        assert not (album / "ios-main/orig-img").exists()
        assert not (album / "ios-main/edit-img").exists()
        assert not (album / "ios-main").exists()
        assert not (album / "main-img").exists()
        assert not (album / "main-jpg").exists()

    def test_plain_removes_by_stem(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_album(album)

        result = rm_media(album, ["nelu-img/sunset.heic"])

        assert result.total > 0
        assert "sunset.heic" not in file_names(album / "nelu-img")
        assert "sunset.jpg" not in file_names(album / "nelu-jpg")
        assert "beach.png" in file_names(album / "nelu-img")

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = rm_media(album, ["main-jpg/IMG_E0410.jpg"], dry_run=True)

        assert result.total > 0
        assert "IMG_0410.HEIC" in file_names(album / "ios-main/orig-img")
        assert "IMG_E0410.jpg" in file_names(album / "main-jpg")

    def test_live_photo_mov_removes_the_whole_live_photo(
        self,
        tmp_path: Path,
    ) -> None:
        album = tmp_path / "album"
        _setup_ios_album_with_live_photo(album)

        result = rm_media(album, ["ios-main/orig-img/IMG_0001.MOV"])

        assert result.total == 5
        assert not (album / "ios-main").exists()
        assert not (album / "main-img").exists()
        assert not (album / "main-jpg").exists()

    def test_ios_video_removes_all_variants(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album_with_video(album)

        result = rm_media(album, ["main-vid/IMG_E0115.MOV"])

        assert result.total > 0
        assert file_names(album / "ios-main/orig-vid") == set()
        assert file_names(album / "ios-main/edit-vid") == set()
        assert file_names(album / "main-vid") == set()


class TestMediaOpSummary:
    def test_summary_counts_files_by_directory(self) -> None:
        assert format_media_op_summary("move", (("orig-img", ("a", "b")),)) == (
            "Done. Moved 2 file(s): 2 from orig-img."
        )

    def test_dry_run_summary_says_what_would_happen(self) -> None:
        assert format_media_op_summary(
            "remove",
            (("orig-img", ("a", "b")),),
            dry_run=True,
        ) == ("Would remove 2 file(s): 2 from orig-img.")

    def test_summary_names_the_verb_when_nothing_matched(self) -> None:
        assert format_media_op_summary("remove", ()) == "Done. No files to remove."
