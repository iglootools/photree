"""Tests for photree.album.importer.image_capture module."""

import os
from pathlib import Path

import pytest

from photree.fs import SELECTION_DIR, LinkMode
from photree.album.importer.image_capture import (
    STAGE_IMPORT_IC,
    STAGE_REFRESH_MAIN_IMG,
    STAGE_REFRESH_MAIN_JPG,
    STAGE_REFRESH_MAIN_VID,
    ImportResult,
    plan_import,
    run_import,
    validate_import_plan,
)


def _noop_convert(_src: Path, _dst_dir: Path, *, dry_run: bool) -> Path | None:
    """No-op converter for tests (avoids calling sips on fake HEIC files)."""
    return None


def _setup_image_capture_dir(tmp_path: Path, filenames: list[str]) -> Path:
    """Create a fake Image Capture directory with the given filenames."""
    ic_dir = tmp_path / "image_capture"
    ic_dir.mkdir()
    for name in filenames:
        (ic_dir / name).write_text("data")
    return ic_dir


def _setup_album(tmp_path: Path, selection_files: list[str]) -> Path:
    """Create an album directory with a to-import/ subfolder."""
    album = tmp_path / "album"
    selection = album / SELECTION_DIR
    selection.mkdir(parents=True)
    for name in selection_files:
        (selection / name).write_text("data")
    return album


# ---------------------------------------------------------------------------
# plan_import
# ---------------------------------------------------------------------------


class TestPlanImport:
    def test_matches_image_by_number(self) -> None:
        plan = plan_import(
            ["IMG_0410.HEIC"],
            ["IMG_0410.HEIC", "IMG_0410.AAE", "IMG_E0410.HEIC", "IMG_O0410.AAE"],
        )
        assert len(plan.matches) == 1
        assert plan.unmatched == ()
        m = plan.matches[0]
        assert m.img_number == "0410"
        assert m.media_type == "image"
        assert "IMG_0410.HEIC" in m.orig_files
        assert "IMG_0410.AAE" in m.orig_files
        assert "IMG_E0410.HEIC" in m.rendered_files
        assert "IMG_O0410.AAE" in m.rendered_files

    def test_matches_video_by_number(self) -> None:
        plan = plan_import(
            ["IMG_0115.MOV"],
            ["IMG_0115.MOV", "IMG_E0115.MOV"],
        )
        assert len(plan.matches) == 1
        m = plan.matches[0]
        assert m.media_type == "video"
        assert "IMG_0115.MOV" in m.orig_files
        assert "IMG_E0115.MOV" in m.rendered_files

    def test_jpeg_selection_matches_heic_ic(self) -> None:
        plan = plan_import(
            ["IMG_0410.JPEG"],
            ["IMG_0410.HEIC", "IMG_0410.AAE"],
        )
        assert len(plan.matches) == 1
        assert plan.unmatched == ()
        assert "IMG_0410.HEIC" in plan.matches[0].orig_files

    def test_unmatched_when_no_ic_original(self) -> None:
        plan = plan_import(
            ["IMG_9999.HEIC"],
            ["IMG_0001.HEIC"],
        )
        assert len(plan.matches) == 0
        assert "IMG_9999.HEIC" in plan.unmatched

    def test_non_media_file_is_unmatched(self) -> None:
        plan = plan_import(
            ["notes.txt"],
            ["IMG_0001.HEIC"],
        )
        assert "notes.txt" in plan.unmatched

    def test_video_does_not_match_image_ic_files(self) -> None:
        plan = plan_import(
            ["IMG_0001.MOV"],
            ["IMG_0001.HEIC", "IMG_0001.AAE"],
        )
        assert len(plan.matches) == 0
        assert "IMG_0001.MOV" in plan.unmatched

    def test_image_does_not_match_video_ic_files(self) -> None:
        plan = plan_import(
            ["IMG_0001.HEIC"],
            ["IMG_0001.MOV"],
        )
        assert len(plan.matches) == 0
        assert "IMG_0001.HEIC" in plan.unmatched

    def test_video_accepts_aae_sidecar(self) -> None:
        # AAE sidecars for videos are unconfirmed but accepted
        plan = plan_import(
            ["IMG_0115.MOV"],
            ["IMG_0115.MOV", "IMG_0115.AAE"],
        )
        assert len(plan.matches) == 1
        assert "IMG_0115.AAE" in plan.matches[0].orig_files


# ---------------------------------------------------------------------------
# validate_import_plan
# ---------------------------------------------------------------------------


class TestValidateImportPlan:
    def test_valid_plan_no_errors(self) -> None:
        plan = plan_import(
            ["IMG_0410.HEIC"],
            ["IMG_0410.HEIC", "IMG_0410.AAE", "IMG_E0410.HEIC", "IMG_O0410.AAE"],
        )
        errors = validate_import_plan(plan)
        assert errors == []

    def test_unmatched_selection_file(self) -> None:
        plan = plan_import(["IMG_9999.HEIC"], ["IMG_0001.HEIC"])
        errors = validate_import_plan(plan)
        assert len(errors) == 1
        assert "no matching original" in errors[0].message

    def test_rendered_without_sidecar(self) -> None:
        plan = plan_import(
            ["IMG_0410.HEIC"],
            ["IMG_0410.HEIC", "IMG_0410.AAE", "IMG_E0410.HEIC"],
        )
        errors = validate_import_plan(plan)
        assert any("rendered sidecar" in e.message for e in errors)

    def test_rendered_sidecar_without_rendered_media(self) -> None:
        plan = plan_import(
            ["IMG_0410.HEIC"],
            ["IMG_0410.HEIC", "IMG_0410.AAE", "IMG_O0410.AAE"],
        )
        errors = validate_import_plan(plan)
        assert any("rendered media" in e.message for e in errors)

    def test_heic_without_aae_warns(self) -> None:
        plan = plan_import(
            ["IMG_0410.HEIC"],
            ["IMG_0410.HEIC"],
        )
        errors = validate_import_plan(plan)
        assert any("no AAE sidecar" in e.message for e in errors)

    def test_png_without_aae_is_fine(self) -> None:
        plan = plan_import(
            ["IMG_0073.PNG"],
            ["IMG_0073.PNG"],
        )
        errors = validate_import_plan(plan)
        assert errors == []

    def test_multiple_orig_media_deduped_with_heic_priority(self) -> None:
        # Dedup resolves duplicate before validation — HEIC wins, JPG dropped
        plan = plan_import(
            ["IMG_0410.HEIC"],
            ["IMG_0410.HEIC", "IMG_0410.JPG", "IMG_0410.AAE"],
        )
        # No validation errors (dedup resolved it)
        errors = validate_import_plan(plan)
        assert not any("expected 1 original media file" in e.message for e in errors)
        # Dedup warning on the plan
        assert any("IMG_0410.JPG dropped" in w for w in plan.dedup_warnings)
        # Only HEIC in the match
        assert len(plan.matches) == 1
        orig_media = [
            f for f in plan.matches[0].orig_files if f.endswith((".HEIC", ".JPG"))
        ]
        assert orig_media == ["IMG_0410.HEIC"]

    def test_multiple_rendered_media_deduped_with_heic_priority(self) -> None:
        plan = plan_import(
            ["IMG_0410.HEIC"],
            [
                "IMG_0410.HEIC",
                "IMG_0410.AAE",
                "IMG_E0410.HEIC",
                "IMG_E0410.JPG",
                "IMG_O0410.AAE",
            ],
        )
        errors = validate_import_plan(plan)
        assert not any(
            "expected at most 1 rendered media file" in e.message for e in errors
        )
        assert any("IMG_E0410.JPG dropped" in w for w in plan.dedup_warnings)
        rendered_media = [
            f for f in plan.matches[0].rendered_files if f.endswith((".HEIC", ".JPG"))
        ]
        assert rendered_media == ["IMG_E0410.HEIC"]


class TestPlanImportProRaw:
    def test_matches_dng_by_number(self) -> None:
        plan = plan_import(
            ["IMG_0235.DNG"],
            ["IMG_0235.DNG", "IMG_0235.AAE", "IMG_E0235.JPG", "IMG_O0235.AAE"],
        )
        assert len(plan.matches) == 1
        m = plan.matches[0]
        assert m.media_type == "image"
        assert "IMG_0235.DNG" in m.orig_files
        assert "IMG_0235.AAE" in m.orig_files
        assert "IMG_E0235.JPG" in m.rendered_files
        assert "IMG_O0235.AAE" in m.rendered_files

    def test_jpeg_selection_matches_dng_ic(self) -> None:
        plan = plan_import(
            ["IMG_0235.JPEG"],
            ["IMG_0235.DNG", "IMG_0235.AAE"],
        )
        assert len(plan.matches) == 1
        assert "IMG_0235.DNG" in plan.matches[0].orig_files

    def test_dng_priority_over_heic_in_dedup(self) -> None:
        plan = plan_import(
            ["IMG_0235.DNG"],
            ["IMG_0235.DNG", "IMG_0235.HEIC", "IMG_0235.AAE"],
        )
        assert any("IMG_0235.HEIC dropped" in w for w in plan.dedup_warnings)
        orig_media = [
            f for f in plan.matches[0].orig_files if f.endswith((".DNG", ".HEIC"))
        ]
        assert orig_media == ["IMG_0235.DNG"]


# ---------------------------------------------------------------------------
# run_import
# ---------------------------------------------------------------------------


class TestRunImport:
    def test_copies_orig_and_rendered_images(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0410.HEIC"])
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            [
                "IMG_0410.HEIC",
                "IMG_0410.AAE",
                "IMG_E0410.HEIC",
                "IMG_O0410.AAE",
            ],
        )

        result = run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert isinstance(result, ImportResult)
        assert result.unprocessed == ()
        # orig
        assert (album / "ios-main/orig-img" / "IMG_0410.HEIC").exists()
        assert (album / "ios-main/orig-img" / "IMG_0410.AAE").exists()
        # rendered
        assert (album / "ios-main/edit-img" / "IMG_E0410.HEIC").exists()
        assert (album / "ios-main/edit-img" / "IMG_O0410.AAE").exists()
        # browsable should have rendered version (not orig)
        assert (album / "main-img" / "IMG_E0410.HEIC").exists()
        assert not (album / "main-img" / "IMG_0410.HEIC").exists()

    def test_browsable_falls_back_to_orig_when_no_rendered(
        self, tmp_path: Path
    ) -> None:
        album = _setup_album(tmp_path, ["IMG_0100.HEIC"])
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0100.HEIC", "IMG_0100.AAE"],
        )

        result = run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )
        assert result.unprocessed == ()
        assert (album / "main-img" / "IMG_0100.HEIC").exists()

    def test_copies_mov_files(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0115.MOV"])
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0115.MOV", "IMG_E0115.MOV"],
        )

        result = run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )
        assert result.unprocessed == ()
        assert (album / "ios-main/orig-vid" / "IMG_0115.MOV").exists()
        assert (album / "ios-main/edit-vid" / "IMG_E0115.MOV").exists()
        assert (album / "main-vid" / "IMG_E0115.MOV").exists()

    def test_removes_processed_selection_files(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert not (album / SELECTION_DIR).exists()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC"])

        run_import(
            album_dir=album,
            image_capture_dir=ic_dir,
            dry_run=True,
            convert_file=_noop_convert,
        )

        assert (album / SELECTION_DIR).exists()
        assert not (album / "ios-main/orig-img").exists()

    def test_error_when_selection_empty(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        (album / SELECTION_DIR).mkdir(parents=True)
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC"])

        with pytest.raises(FileNotFoundError, match=SELECTION_DIR):
            run_import(
                album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
            )

    def test_error_when_image_capture_empty(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])
        ic_dir = tmp_path / "image_capture"
        ic_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="image capture"):
            run_import(
                album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
            )

    def test_only_imports_files_matching_selection(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0002.HEIC", "IMG_0003.HEIC"],
        )

        run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert (album / "ios-main/orig-img" / "IMG_0001.HEIC").exists()
        assert not (album / "ios-main/orig-img" / "IMG_0002.HEIC").exists()
        assert not (album / "ios-main/orig-img" / "IMG_0003.HEIC").exists()

    def test_returns_import_result_with_processed(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0001.HEIC", "IMG_0002.MOV"])
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0002.MOV"],
        )

        result = run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert "IMG_0001.HEIC" in result.processed
        assert "IMG_0002.MOV" in result.processed
        assert result.unprocessed == ()

    def test_stage_callbacks_called_in_order(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0001.HEIC"])
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC", "IMG_0001.AAE"])

        stages: list[tuple[str, str]] = []
        run_import(
            album_dir=album,
            image_capture_dir=ic_dir,
            convert_file=_noop_convert,
            on_stage_start=lambda s: stages.append(("start", s)),
            on_stage_end=lambda s: stages.append(("end", s)),
        )

        assert stages == [
            ("start", STAGE_IMPORT_IC),
            ("end", STAGE_IMPORT_IC),
            ("start", STAGE_REFRESH_MAIN_IMG),
            ("end", STAGE_REFRESH_MAIN_IMG),
            ("start", STAGE_REFRESH_MAIN_VID),
            ("end", STAGE_REFRESH_MAIN_VID),
            ("start", STAGE_REFRESH_MAIN_JPG),
            ("end", STAGE_REFRESH_MAIN_JPG),
        ]

    def test_refuses_to_overwrite_existing_files(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0410.HEIC"])
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0410.HEIC", "IMG_0410.AAE"])

        # First import succeeds
        run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        # Re-create selection and IC files for a second import attempt
        (album / SELECTION_DIR).mkdir(parents=True, exist_ok=True)
        (album / SELECTION_DIR / "IMG_0410.HEIC").write_text("data")
        round2 = tmp_path / "round2"
        round2.mkdir()
        ic_dir2 = _setup_image_capture_dir(round2, ["IMG_0410.HEIC", "IMG_0410.AAE"])

        with pytest.raises(ValueError, match="would conflict"):
            run_import(
                album_dir=album,
                image_capture_dir=ic_dir2,
                convert_file=_noop_convert,
            )


class TestRunImportLinkMode:
    def test_default_creates_hardlinks_in_browsable(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0410.HEIC"])
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0410.HEIC", "IMG_0410.AAE", "IMG_E0410.HEIC", "IMG_O0410.AAE"],
        )

        run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        # Browsable should be hardlinked to rendered
        browsable = album / "main-img" / "IMG_E0410.HEIC"
        rendered = album / "ios-main/edit-img" / "IMG_E0410.HEIC"
        assert os.stat(browsable).st_ino == os.stat(rendered).st_ino

        # Orig files should be copies (not hardlinks to IC dir)
        orig = album / "ios-main/orig-img" / "IMG_0410.HEIC"
        ic_file = ic_dir / "IMG_0410.HEIC"
        assert os.stat(orig).st_ino != os.stat(ic_file).st_ino

    def test_symlink_mode_creates_symlinks_in_browsable(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0100.HEIC"])
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0100.HEIC", "IMG_0100.AAE"])

        run_import(
            album_dir=album,
            image_capture_dir=ic_dir,
            link_mode=LinkMode.SYMLINK,
            convert_file=_noop_convert,
        )

        browsable = album / "main-img" / "IMG_0100.HEIC"
        assert browsable.is_symlink()
        assert not os.path.isabs(os.readlink(browsable))
        assert (
            browsable.resolve()
            == (album / "ios-main/orig-img" / "IMG_0100.HEIC").resolve()
        )

    def test_copy_mode_creates_independent_copies(self, tmp_path: Path) -> None:
        album = _setup_album(tmp_path, ["IMG_0100.HEIC"])
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0100.HEIC", "IMG_0100.AAE"])

        run_import(
            album_dir=album,
            image_capture_dir=ic_dir,
            link_mode=LinkMode.COPY,
            convert_file=_noop_convert,
        )

        browsable = album / "main-img" / "IMG_0100.HEIC"
        orig = album / "ios-main/orig-img" / "IMG_0100.HEIC"
        assert not browsable.is_symlink()
        assert os.stat(browsable).st_ino != os.stat(orig).st_ino
