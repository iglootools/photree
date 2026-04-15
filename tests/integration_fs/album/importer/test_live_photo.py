"""Tests for iOS Live Photo support in import and browsable workflows."""

from pathlib import Path

from photree.album.importer.image_capture import (
    MediaType,
    plan_import,
    run_import,
    validate_import_plan,
)
from photree.album.jpeg import noop_convert_single
from photree.album.live_photo import (
    compute_live_photo_videos,
    detect_live_photo_keys,
)
from photree.album.store.protocol import (
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    SELECTION_DIR,
    ios_media_source,
)
from photree.album.store.media_sources import ios_img_number
from photree.common.fs import list_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)


def _setup_ic(tmp_path: Path, filenames: list[str]) -> Path:
    ic = tmp_path / "ic"
    ic.mkdir()
    for f in filenames:
        (ic / f).write_text("data")
    return ic


def _setup_album(tmp_path: Path, selection: list[str]) -> Path:
    album = tmp_path / "album"
    sel_dir = album / SELECTION_DIR
    sel_dir.mkdir(parents=True)
    for f in selection:
        (sel_dir / f).write_text("data")
    return album


# ---------------------------------------------------------------------------
# detect_live_photo_keys
# ---------------------------------------------------------------------------


class TestDetectLivePhotoKeys:
    def test_detects_matching_image_and_video(self, tmp_path: Path) -> None:
        d = tmp_path / "orig-img"
        d.mkdir()
        (d / "IMG_0001.HEIC").write_text("img")
        (d / "IMG_0001.MOV").write_text("vid")
        (d / "IMG_0001.AAE").write_text("sidecar")

        keys = detect_live_photo_keys(
            d, IOS_IMG_EXTENSIONS, IOS_VID_EXTENSIONS, ios_img_number
        )
        assert keys == frozenset({"0001"})

    def test_no_live_photo_when_image_only(self, tmp_path: Path) -> None:
        d = tmp_path / "orig-img"
        d.mkdir()
        (d / "IMG_0001.HEIC").write_text("img")

        keys = detect_live_photo_keys(
            d, IOS_IMG_EXTENSIONS, IOS_VID_EXTENSIONS, ios_img_number
        )
        assert keys == frozenset()

    def test_no_live_photo_when_video_only(self, tmp_path: Path) -> None:
        d = tmp_path / "orig-img"
        d.mkdir()
        (d / "IMG_0001.MOV").write_text("vid")

        keys = detect_live_photo_keys(
            d, IOS_IMG_EXTENSIONS, IOS_VID_EXTENSIONS, ios_img_number
        )
        assert keys == frozenset()

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        keys = detect_live_photo_keys(
            tmp_path / "nope",
            IOS_IMG_EXTENSIONS,
            IOS_VID_EXTENSIONS,
            ios_img_number,
        )
        assert keys == frozenset()


# ---------------------------------------------------------------------------
# compute_live_photo_videos
# ---------------------------------------------------------------------------


class TestComputeLivePhotoVideos:
    def test_picks_original_when_no_edit(self, tmp_path: Path) -> None:
        orig = tmp_path / "orig"
        orig.mkdir()
        (orig / "IMG_0001.MOV").write_text("orig-vid")
        edit = tmp_path / "edit"

        videos = compute_live_photo_videos(
            orig, edit, IOS_VID_EXTENSIONS, ios_img_number
        )
        assert videos == [("IMG_0001.MOV", orig)]

    def test_picks_edited_when_available(self, tmp_path: Path) -> None:
        orig = tmp_path / "orig"
        orig.mkdir()
        (orig / "IMG_0001.MOV").write_text("orig-vid")
        edit = tmp_path / "edit"
        edit.mkdir()
        (edit / "IMG_E0001.MOV").write_text("edit-vid")

        videos = compute_live_photo_videos(
            orig, edit, IOS_VID_EXTENSIONS, ios_img_number
        )
        assert videos == [("IMG_E0001.MOV", edit)]


# ---------------------------------------------------------------------------
# plan_import — Live Photo detection
# ---------------------------------------------------------------------------


class TestPlanImportLivePhoto:
    def test_image_selection_detects_live_photo(self) -> None:
        plan = plan_import(
            ["IMG_0001.HEIC"],
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        assert len(plan.matches) == 1
        m = plan.matches[0]
        assert m.is_live_photo is True
        assert m.media_type == MediaType.IMAGE
        assert "IMG_0001.HEIC" in m.orig_files
        assert "IMG_0001.MOV" in m.companion_orig_files

    def test_video_selection_detects_live_photo(self) -> None:
        plan = plan_import(
            ["IMG_0001.MOV"],
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        assert len(plan.matches) == 1
        m = plan.matches[0]
        assert m.is_live_photo is True
        assert m.media_type == MediaType.VIDEO
        assert "IMG_0001.MOV" in m.orig_files
        assert "IMG_0001.HEIC" in m.companion_orig_files

    def test_no_live_photo_when_image_only(self) -> None:
        plan = plan_import(
            ["IMG_0001.HEIC"],
            ["IMG_0001.HEIC", "IMG_0001.AAE"],
        )
        assert len(plan.matches) == 1
        assert plan.matches[0].is_live_photo is False
        assert plan.matches[0].companion_orig_files == ()

    def test_no_live_photo_when_video_only(self) -> None:
        plan = plan_import(
            ["IMG_0001.MOV"],
            ["IMG_0001.MOV"],
        )
        assert len(plan.matches) == 1
        assert plan.matches[0].is_live_photo is False

    def test_live_photo_with_edits(self) -> None:
        plan = plan_import(
            ["IMG_0001.HEIC"],
            [
                "IMG_0001.HEIC",
                "IMG_0001.AAE",
                "IMG_0001.MOV",
                "IMG_E0001.HEIC",
                "IMG_O0001.AAE",
                "IMG_E0001.MOV",
            ],
        )
        assert len(plan.matches) == 1
        m = plan.matches[0]
        assert m.is_live_photo is True
        assert "IMG_E0001.MOV" in m.companion_rendered_files

    def test_live_photo_validates_ok(self) -> None:
        plan = plan_import(
            ["IMG_0001.HEIC"],
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        errors, warnings = validate_import_plan(plan)
        assert errors == []

    def test_image_only_ic_not_matched_by_video_selection(self) -> None:
        """Video selection with image-only IC → unmatched (not a Live Photo)."""
        plan = plan_import(
            ["IMG_0001.MOV"],
            ["IMG_0001.HEIC", "IMG_0001.AAE"],
        )
        assert len(plan.matches) == 0
        assert "IMG_0001.MOV" in plan.unmatched


# ---------------------------------------------------------------------------
# run_import — Live Photo file routing
# ---------------------------------------------------------------------------


class TestRunImportLivePhoto:
    def test_image_selection_routes_both_to_orig_img(self, tmp_path: Path) -> None:
        ic = _setup_ic(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        orig_img_files = list_files(album / ms.orig_img_dir)
        assert "IMG_0001.HEIC" in orig_img_files
        assert "IMG_0001.MOV" in orig_img_files
        assert "IMG_0001.AAE" in orig_img_files

        # orig-vid should NOT contain Live Photo video
        orig_vid = album / ms.orig_vid_dir
        assert not orig_vid.exists() or "IMG_0001.MOV" not in list_files(orig_vid)

    def test_video_selection_routes_both_to_orig_img(self, tmp_path: Path) -> None:
        ic = _setup_ic(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        album = _setup_album(tmp_path, ["IMG_0001.MOV"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        orig_img_files = list_files(album / ms.orig_img_dir)
        assert "IMG_0001.HEIC" in orig_img_files
        assert "IMG_0001.MOV" in orig_img_files

    def test_browsable_img_contains_live_photo_video(self, tmp_path: Path) -> None:
        ic = _setup_ic(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        img_files = list_files(album / ms.img_dir)
        assert "IMG_0001.HEIC" in img_files
        assert "IMG_0001.MOV" in img_files

    def test_browsable_vid_does_not_contain_live_photo_video(
        self, tmp_path: Path
    ) -> None:
        ic = _setup_ic(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        vid_dir = album / ms.vid_dir
        assert not vid_dir.exists() or "IMG_0001.MOV" not in list_files(vid_dir)

    def test_browsable_jpg_does_not_contain_video(self, tmp_path: Path) -> None:
        ic = _setup_ic(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0001.MOV"],
        )
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        jpg_dir = album / ms.jpg_dir
        if jpg_dir.exists():
            jpg_files = list_files(jpg_dir)
            assert all(not f.endswith(".MOV") for f in jpg_files)

    def test_live_photo_with_edits_routes_correctly(self, tmp_path: Path) -> None:
        ic = _setup_ic(
            tmp_path,
            [
                "IMG_0001.HEIC",
                "IMG_0001.AAE",
                "IMG_0001.MOV",
                "IMG_E0001.HEIC",
                "IMG_O0001.AAE",
                "IMG_E0001.MOV",
            ],
        )
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        orig_img = list_files(album / ms.orig_img_dir)
        assert "IMG_0001.HEIC" in orig_img
        assert "IMG_0001.MOV" in orig_img

        edit_img = list_files(album / ms.edit_img_dir)
        assert "IMG_E0001.HEIC" in edit_img
        assert "IMG_E0001.MOV" in edit_img

    def test_standalone_video_still_goes_to_orig_vid(self, tmp_path: Path) -> None:
        """Non-Live-Photo videos are routed to orig-vid as before."""
        ic = _setup_ic(tmp_path, ["IMG_0001.MOV"])
        album = _setup_album(tmp_path, ["IMG_0001.MOV"])

        run_import(
            album_dir=album,
            image_capture_dir=ic,
            convert_file=noop_convert_single,
        )

        ms = ios_media_source("main")
        orig_vid_files = list_files(album / ms.orig_vid_dir)
        assert "IMG_0001.MOV" in orig_vid_files

        # orig-img should not contain the standalone video
        orig_img = album / ms.orig_img_dir
        assert not orig_img.exists() or "IMG_0001.MOV" not in list_files(orig_img)

    def test_collision_check_for_live_photo(self, tmp_path: Path) -> None:
        """Live Photo collision checked against orig-img, not orig-vid."""
        ic = _setup_ic(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.MOV"],
        )
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])

        # Pre-populate orig-img with conflicting number
        ms = ios_media_source("main")
        existing = album / ms.orig_img_dir
        existing.mkdir(parents=True)
        (existing / "IMG_0001.HEIC").write_text("existing")

        import pytest

        with pytest.raises(ValueError, match="conflict"):
            run_import(
                album_dir=album,
                image_capture_dir=ic,
                convert_file=noop_convert_single,
            )


# ---------------------------------------------------------------------------
# iOS integrity check with Live Photos
# ---------------------------------------------------------------------------


class TestCheckWithLivePhotos:
    def test_duplicate_numbers_allows_live_photo(self, tmp_path: Path) -> None:
        from photree.album.check.ios import check_duplicate_numbers

        d = tmp_path / "orig-img"
        d.mkdir()
        (d / "IMG_0001.HEIC").write_text("img")
        (d / "IMG_0001.MOV").write_text("vid")

        all_media = IOS_IMG_EXTENSIONS | IOS_VID_EXTENSIONS
        dupes = check_duplicate_numbers(d, all_media, IOS_IMG_EXTENSIONS)
        assert dupes == ()

    def test_duplicate_numbers_still_flags_real_duplicates(
        self, tmp_path: Path
    ) -> None:
        from photree.album.check.ios import check_duplicate_numbers

        d = tmp_path / "edit-img"
        d.mkdir()
        (d / "IMG_E0001.HEIC").write_text("img1")
        (d / "IMG_E0001.JPG").write_text("img2")

        all_media = IOS_IMG_EXTENSIONS | IOS_VID_EXTENSIONS
        dupes = check_duplicate_numbers(d, all_media, IOS_IMG_EXTENSIONS)
        assert len(dupes) == 1
        assert "0001" in dupes[0]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestLivePhotoStats:
    def test_count_live_photos(self, tmp_path: Path) -> None:
        from photree.album.stats.scan import count_live_photos

        ms = ios_media_source("main")
        orig = tmp_path / ms.orig_img_dir
        orig.mkdir(parents=True)
        (orig / "IMG_0001.HEIC").write_text("img")
        (orig / "IMG_0001.MOV").write_text("vid")
        (orig / "IMG_0002.HEIC").write_text("img2")

        count = count_live_photos(tmp_path, ms, has_archive=True)
        assert count == 1

    def test_count_live_photos_no_archive(self, tmp_path: Path) -> None:
        from photree.album.stats.scan import count_live_photos

        ms = ios_media_source("main")
        count = count_live_photos(tmp_path, ms, has_archive=False)
        assert count == 0
