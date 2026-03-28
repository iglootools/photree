"""Integration test: full demo workflow (seed → import → check → optimize → export).

Mirrors the demo.sh script with assertions at each stage.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from photree.album.integrity import check_ios_album_integrity
from photree.album.jpeg import convert_single_file, copy_convert_single
from photree.album.optimize import optimize_album
from photree.album.preflight import (
    AlbumType,
    detect_album_type,
    run_album_preflight,
)
from photree.exporter.export import AlbumShareLayout, compute_target_dir, export_album
from photree.fsprotocol import (
    MAIN_CONTRIBUTOR,
    SHARE_SENTINEL,
    LinkMode,
    ShareDirectoryLayout,
)
from photree.importer.image_capture import run_import
from photree.importer.testkit import seed_demo


class TestDemoWorkflow:
    """Full end-to-end workflow: seed → import → check → optimize → export."""

    def test_full_workflow(self, tmp_path: Path) -> None:
        # ── Seed ─────────────────────────────────────────────
        result = seed_demo(tmp_path, album_name="2024-06-15 - Demo Album")
        ic_dir = result.image_capture_dir
        album_dir = result.album_dir

        assert ic_dir.is_dir()
        assert album_dir.is_dir()
        assert (album_dir / "to-import").is_dir()

        ic_files = sorted(f.name for f in ic_dir.iterdir())
        assert "IMG_0001.HEIC" in ic_files
        assert "IMG_0003.DNG" in ic_files
        assert "IMG_0006.MOV" in ic_files

        sel_files = sorted(f.name for f in (album_dir / "to-import").iterdir())
        assert len(sel_files) == 6
        # IMG_0004 intentionally excluded from selection
        assert "IMG_0004.JPG" not in sel_files

        # ── Import ───────────────────────────────────────────
        # Use noop converter on Linux where sips is unavailable
        converter = (
            convert_single_file
            if shutil.which("sips") is not None
            else copy_convert_single
        )
        import_result = run_import(
            album_dir=album_dir,
            image_capture_dir=ic_dir,
            link_mode=LinkMode.COPY,
            convert_file=converter,
        )

        assert len(import_result.plan.matches) == 6
        assert len(import_result.plan.unmatched) == 0
        assert len(import_result.unprocessed) == 0

        # iOS directory structure created
        assert (album_dir / MAIN_CONTRIBUTOR.ios_dir).is_dir()
        assert detect_album_type(album_dir) == AlbumType.IOS

        # Originals imported
        assert (album_dir / MAIN_CONTRIBUTOR.orig_img_dir).is_dir()
        orig_img_files = sorted(os.listdir(album_dir / MAIN_CONTRIBUTOR.orig_img_dir))
        assert "IMG_0001.HEIC" in orig_img_files
        assert "IMG_0001.AAE" in orig_img_files
        assert "IMG_0003.DNG" in orig_img_files
        assert "IMG_0005.PNG" in orig_img_files

        # Edits imported
        assert (album_dir / MAIN_CONTRIBUTOR.edit_img_dir).is_dir()
        edit_img_files = sorted(os.listdir(album_dir / MAIN_CONTRIBUTOR.edit_img_dir))
        assert "IMG_E0001.HEIC" in edit_img_files
        assert "IMG_E0003.JPG" in edit_img_files

        # Videos imported
        assert (album_dir / MAIN_CONTRIBUTOR.orig_vid_dir).is_dir()
        assert "IMG_0006.MOV" in os.listdir(album_dir / MAIN_CONTRIBUTOR.orig_vid_dir)
        assert "IMG_0007.MOV" in os.listdir(album_dir / MAIN_CONTRIBUTOR.orig_vid_dir)
        assert (album_dir / MAIN_CONTRIBUTOR.edit_vid_dir).is_dir()
        assert "IMG_E0007.MOV" in os.listdir(album_dir / MAIN_CONTRIBUTOR.edit_vid_dir)

        # Main directories created
        assert (album_dir / MAIN_CONTRIBUTOR.img_dir).is_dir()
        assert (album_dir / MAIN_CONTRIBUTOR.vid_dir).is_dir()
        assert (album_dir / MAIN_CONTRIBUTOR.jpg_dir).is_dir()

        # Main-img picks edit when available, orig otherwise
        main_img_files = sorted(os.listdir(album_dir / MAIN_CONTRIBUTOR.img_dir))
        assert "IMG_E0001.HEIC" in main_img_files  # edit preferred
        assert "IMG_0002.HEIC" in main_img_files  # no edit, orig used
        assert "IMG_0005.PNG" in main_img_files  # screenshot

        # Main-vid picks edit when available
        main_vid_files = sorted(os.listdir(album_dir / MAIN_CONTRIBUTOR.vid_dir))
        assert "IMG_0006.MOV" in main_vid_files  # no edit
        assert "IMG_E0007.MOV" in main_vid_files  # edit preferred

        # Selection files cleaned up
        assert (
            not (album_dir / "to-import").exists()
            or len(os.listdir(album_dir / "to-import")) == 0
        )

        # ── Check ────────────────────────────────────────────
        preflight = run_album_preflight(album_dir, checksum=True)

        assert preflight.album_type == AlbumType.IOS
        assert preflight.dir_check.success
        assert preflight.integrity is not None
        assert preflight.integrity.success

        # ── Optimize (symlinks) ──────────────────────────────
        optimize_album(album_dir, link_mode=LinkMode.SYMLINK)

        # Main-img files should now be symlinks
        for name in main_img_files:
            p = album_dir / MAIN_CONTRIBUTOR.img_dir / name
            assert p.is_symlink(), f"{name} should be a symlink after optimize"

        # Main-vid files should now be symlinks
        for name in main_vid_files:
            p = album_dir / MAIN_CONTRIBUTOR.vid_dir / name
            assert p.is_symlink(), f"{name} should be a symlink after optimize"

        # Main-jpg should NOT be symlinks (JPEG conversions)
        for name in os.listdir(album_dir / MAIN_CONTRIBUTOR.jpg_dir):
            p = album_dir / MAIN_CONTRIBUTOR.jpg_dir / name
            assert not p.is_symlink(), f"{name} in main-jpg should not be a symlink"

        # Integrity still passes after optimization
        integrity_after = check_ios_album_integrity(album_dir, checksum=True)
        assert integrity_after.success

        # ── Export (main-only) ───────────────────────────────
        share_dir = tmp_path / "share"
        share_dir.mkdir()
        (share_dir / SHARE_SENTINEL).touch()

        target_dir = compute_target_dir(
            share_dir, album_dir.name, ShareDirectoryLayout.FLAT
        )
        export_result = export_album(
            album_dir,
            target_dir,
            album_layout=AlbumShareLayout.MAIN_ONLY,
            link_mode=LinkMode.COPY,
        )

        assert export_result.album_type == AlbumType.IOS
        assert export_result.files_copied > 0

        # Exported structure: img/, jpg/, vid/ (main- prefix stripped)
        exported = target_dir
        assert (exported / "main-img").is_dir()
        assert (exported / "main-jpg").is_dir()
        assert (exported / "main-vid").is_dir()

        # iOS internal dirs should NOT be exported
        assert not (exported / MAIN_CONTRIBUTOR.ios_dir).exists()

        # Exported img/ matches main-img content
        exported_img = sorted(os.listdir(exported / "main-img"))
        assert exported_img == main_img_files

        # Exported vid/ matches main-vid content
        exported_vid = sorted(os.listdir(exported / "main-vid"))
        assert exported_vid == main_vid_files
