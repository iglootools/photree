"""
Integration test: full demo workflow (seed → import → check → export).

Mirrors the demo.sh script with assertions at each stage. It runs the same
code on every platform: JPEG conversion is faked and exiftool is not used, so
the outcome never depends on what the developer has installed. Real sips and
exiftool are covered by the tests dedicated to them, which skip where the tool
is missing.
"""

from pathlib import Path

from photree.album.check import run_album_check
from photree.album.exporter.single import compute_target_dir, export_album
from photree.album.importer.album_import import run_import
from photree.album.importer.testkit import seed_demo
from photree.album.store.album_discovery import is_album
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.album.store.metadata import load_album_metadata
from photree.album.store.protocol import ALBUM_YAML
from photree.foundation.layout import PHOTREE_DIR, SHARE_SENTINEL
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout
from tests.fakes import copy_convert_single


class TestDemoWorkflow:
    def test_full_workflow(self, tmp_path: Path) -> None:
        album_dir, ic_dir = _seed(tmp_path)
        _import(album_dir, ic_dir)
        _assert_archive_dirs(album_dir)
        main_vid_files = _assert_browsable_dirs(album_dir)
        _assert_check_passes(album_dir)
        _export_and_assert(tmp_path, album_dir, main_vid_files)


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    """Seed the demo album and its Image Capture dir; return both."""
    result = seed_demo(tmp_path, album_name="2024-06-15 - Demo Album")
    ic_dir = result.image_capture_dir
    album_dir = result.album_dir

    assert ic_dir.is_dir()
    assert album_dir.is_dir()
    assert (album_dir / "to-import-ios-main").is_dir()

    ic_files = sorted(f.name for f in ic_dir.iterdir())
    assert "IMG_0001.HEIC" in ic_files
    assert "IMG_0003.DNG" in ic_files
    assert "IMG_0006.MOV" in ic_files

    sel_files = sorted(f.name for f in (album_dir / "to-import-ios-main").iterdir())
    assert len(sel_files) == 8
    # IMG_0004 intentionally excluded from selection
    assert "IMG_0004.JPG" not in sel_files
    return album_dir, ic_dir


def _import(album_dir: Path, ic_dir: Path) -> None:
    import_result = run_import(
        album_dir=album_dir,
        image_capture_dir=ic_dir,
        link_mode=LinkMode.COPY,
        convert_file=copy_convert_single,
    )

    assert len(import_result.ios_results) == 1
    main_plan = import_result.ios_results[0].plan
    assert len(main_plan.matches) == 8
    assert len(main_plan.unmatched) == 0
    assert len(import_result.unprocessed) == 0

    assert (album_dir / PHOTREE_DIR).is_dir()
    assert (album_dir / PHOTREE_DIR / ALBUM_YAML).is_file()
    assert load_album_metadata(album_dir) is not None
    assert is_album(album_dir)
    assert (album_dir / MAIN_MEDIA_SOURCE.archive_dir).is_dir()
    assert any(ms.is_ios for ms in discover_media_sources(album_dir))
    assert (
        not (album_dir / "to-import-ios-main").exists()
        or len([p.name for p in (album_dir / "to-import-ios-main").iterdir()]) == 0
    )


def _assert_archive_dirs(album_dir: Path) -> None:
    assert (album_dir / MAIN_MEDIA_SOURCE.orig_img_dir).is_dir()
    orig_img_files = sorted(
        [p.name for p in (album_dir / MAIN_MEDIA_SOURCE.orig_img_dir).iterdir()],
    )
    assert "IMG_0001.HEIC" in orig_img_files
    assert "IMG_0001.AAE" in orig_img_files
    assert "IMG_0003.DNG" in orig_img_files
    assert "IMG_0005.PNG" in orig_img_files
    # Live Photos: both image + companion video in orig-img
    assert "IMG_0008.HEIC" in orig_img_files
    assert "IMG_0008.MOV" in orig_img_files
    assert "IMG_0009.HEIC" in orig_img_files
    assert "IMG_0009.MOV" in orig_img_files

    assert (album_dir / MAIN_MEDIA_SOURCE.edit_img_dir).is_dir()
    edit_img_files = sorted(
        [p.name for p in (album_dir / MAIN_MEDIA_SOURCE.edit_img_dir).iterdir()],
    )
    assert "IMG_E0001.HEIC" in edit_img_files
    assert "IMG_E0003.JPG" in edit_img_files
    # Live Photo edits in edit-img
    assert "IMG_E0009.HEIC" in edit_img_files
    assert "IMG_E0009.MOV" in edit_img_files

    assert (album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir).is_dir()
    assert "IMG_0006.MOV" in [
        p.name for p in (album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir).iterdir()
    ]
    assert "IMG_0007.MOV" in [
        p.name for p in (album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir).iterdir()
    ]
    assert (album_dir / MAIN_MEDIA_SOURCE.edit_vid_dir).is_dir()
    assert "IMG_E0007.MOV" in [
        p.name for p in (album_dir / MAIN_MEDIA_SOURCE.edit_vid_dir).iterdir()
    ]


def _assert_browsable_dirs(album_dir: Path) -> list[str]:
    """Assert main-img and main-vid pick edits over originals; return main-vid."""
    assert (album_dir / MAIN_MEDIA_SOURCE.img_dir).is_dir()
    assert (album_dir / MAIN_MEDIA_SOURCE.vid_dir).is_dir()
    assert (album_dir / MAIN_MEDIA_SOURCE.jpg_dir).is_dir()

    # Main-img picks edit when available, orig otherwise
    main_img_files = sorted(
        [p.name for p in (album_dir / MAIN_MEDIA_SOURCE.img_dir).iterdir()],
    )
    assert "IMG_E0001.HEIC" in main_img_files  # edit preferred
    assert "IMG_0002.HEIC" in main_img_files  # no edit, orig used
    assert "IMG_0005.PNG" in main_img_files  # screenshot
    # Live Photo: both image and companion video in main-img
    assert "IMG_0008.HEIC" in main_img_files
    assert "IMG_0008.MOV" in main_img_files
    assert "IMG_E0009.HEIC" in main_img_files  # edit preferred
    assert "IMG_E0009.MOV" in main_img_files  # edit preferred

    # Main-vid picks edit when available
    main_vid_files = sorted(
        [p.name for p in (album_dir / MAIN_MEDIA_SOURCE.vid_dir).iterdir()],
    )
    assert "IMG_0006.MOV" in main_vid_files  # no edit
    assert "IMG_E0007.MOV" in main_vid_files  # edit preferred
    return main_vid_files


def _assert_check_passes(album_dir: Path) -> None:
    preflight = run_album_check(
        album_dir,
        exiftool=None,
        link_mode=LinkMode.COPY,
        checksum=True,
    )

    assert preflight.media_source_summary.has_ios
    assert preflight.dir_check.success
    assert preflight.integrity is not None
    assert preflight.integrity.success


def _export_and_assert(
    tmp_path: Path,
    album_dir: Path,
    main_vid_files: list[str],
) -> None:
    share_dir = tmp_path / "share"
    share_dir.mkdir()
    (share_dir / SHARE_SENTINEL).touch()

    target_dir = compute_target_dir(
        share_dir,
        album_dir.name,
        ShareDirectoryLayout.FLAT,
    )
    export_result = export_album(
        album_dir,
        target_dir,
        album_layout=AlbumShareLayout.BROWSABLE_JPG,
        link_mode=LinkMode.COPY,
    )

    assert export_result.album_type == "ios"
    assert export_result.files_copied > 0

    assert not (target_dir / "main-img").exists()
    assert (target_dir / "main-jpg").is_dir()
    assert (target_dir / "main-vid").is_dir()
    assert not (target_dir / MAIN_MEDIA_SOURCE.archive_dir).exists()
    assert (
        sorted([p.name for p in (target_dir / "main-vid").iterdir()]) == main_vid_files
    )
