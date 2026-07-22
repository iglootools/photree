"""Tests for std (non-iOS) import: photree.album.importer.std and orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.album.importer.album_import import run_import, validate_album_import
from photree.album.importer.std import import_std_source, validate_std_task
from photree.album.importer.tasks import discover_import_tasks
from photree.album.store.protocol import (
    ios_import_dir,
    std_import_dir,
    std_media_source,
)
from photree.common.fs import list_files


def _noop_convert(_src: Path, _dst_dir: Path, *, dry_run: bool) -> Path | None:
    return None


def _setup_std_staging(
    album: Path,
    name: str,
    *,
    orig: list[str] | None = None,
    edit: list[str] | None = None,
) -> Path:
    """Create a to-import-std-<name>/ staging dir with orig/ and edit/ files."""
    staging = album / std_import_dir(name)
    for sub, files in (("orig", orig or []), ("edit", edit or [])):
        if files:
            (staging / sub).mkdir(parents=True)
            for f in files:
                (staging / sub / f).write_text("data")
    return staging


def _std_task(album: Path, name: str):
    (task,) = [t for t in discover_import_tasks(album) if t.name == name and t.is_std]
    return task


class TestValidateStdTask:
    def test_valid(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_staging(album, "nelu", orig=["a.jpg"], edit=["a.jpg"])
        assert validate_std_task(_std_task(album, "nelu")) == []

    def test_empty_reports_error(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        (album / std_import_dir("nelu")).mkdir(parents=True)
        errors = validate_std_task(_std_task(album, "nelu"))
        assert any("no media files" in e for e in errors)

    def test_duplicate_stems_rejected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_staging(album, "nelu", orig=["a.jpg", "a.heic"])
        errors = validate_std_task(_std_task(album, "nelu"))
        assert any("multiple media files" in e for e in errors)

    def test_orphan_edit_allowed(self, tmp_path: Path) -> None:
        # An edit with no matching orig is allowed (matches existing std behavior).
        album = tmp_path / "album"
        _setup_std_staging(album, "nelu", orig=["a.jpg"], edit=["b.jpg"])
        assert validate_std_task(_std_task(album, "nelu")) == []


class TestImportStdSource:
    def test_splits_by_extension(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        _setup_std_staging(
            album,
            "nelu",
            orig=["photo.jpg", "clip.mov"],
            edit=["photo.jpg"],
        )
        ms = std_media_source("nelu")
        result = import_std_source(album, _std_task(album, "nelu"))

        assert result.imported == 3
        assert "photo.jpg" in list_files(album / ms.orig_img_dir)
        assert "clip.mov" in list_files(album / ms.orig_vid_dir)
        assert "photo.jpg" in list_files(album / ms.edit_img_dir)

    def test_consumes_staging_dir_on_success(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        staging = _setup_std_staging(album, "nelu", orig=["a.jpg"])
        import_std_source(album, _std_task(album, "nelu"))
        assert not staging.exists()

    def test_dry_run_leaves_staging_and_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        staging = _setup_std_staging(album, "nelu", orig=["a.jpg"])
        ms = std_media_source("nelu")
        import_std_source(album, _std_task(album, "nelu"), dry_run=True)
        assert staging.exists()
        assert not (album / ms.orig_img_dir).exists()

    def test_skips_non_media(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        _setup_std_staging(album, "nelu", orig=["a.jpg", "notes.txt"])
        result = import_std_source(album, _std_task(album, "nelu"))
        assert result.imported == 1
        assert any("notes.txt" in s for s in result.skipped_non_media)

    def test_collision_guard(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = std_media_source("nelu")
        (album / ms.orig_img_dir).mkdir(parents=True)
        (album / ms.orig_img_dir / "a.jpg").write_text("existing")
        _setup_std_staging(album, "nelu", orig=["a.jpg"])

        with pytest.raises(ValueError, match="conflict"):
            import_std_source(album, _std_task(album, "nelu"))


class TestRunImportStd:
    def test_std_only_import_builds_browsable(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-01-01 - Trip"
        album.mkdir()
        _setup_std_staging(album, "nelu", orig=["photo.jpg"])
        ms = std_media_source("nelu")

        # Std-only import needs no Image Capture dir.
        result = run_import(
            album_dir=album,
            image_capture_dir=tmp_path / "nonexistent-ic",
            convert_file=_noop_convert,
        )

        assert len(result.std_results) == 1
        assert (album / ".photree" / "album.yaml").is_file()
        assert "photo.jpg" in list_files(album / ms.img_dir)
        assert not (album / std_import_dir("nelu")).exists()

    def test_mixed_ios_and_std_in_one_run(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-01-01 - Trip"
        album.mkdir()
        # iOS selection
        sel = album / ios_import_dir("main")
        sel.mkdir(parents=True)
        (sel / "IMG_0001.HEIC").write_text("data")
        # std staging
        _setup_std_staging(album, "nelu", orig=["photo.jpg"])

        ic_dir = tmp_path / "ic"
        ic_dir.mkdir()
        (ic_dir / "IMG_0001.HEIC").write_text("data")
        (ic_dir / "IMG_0001.AAE").write_text("data")

        result = run_import(
            album_dir=album, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert len(result.ios_results) == 1
        assert len(result.std_results) == 1
        assert (album / "ios-main/orig-img" / "IMG_0001.HEIC").exists()
        assert (album / "std-nelu/orig-img" / "photo.jpg").exists()
        # Both browsable dirs built
        assert "IMG_0001.HEIC" in list_files(album / "main-img")
        assert "photo.jpg" in list_files(album / "nelu-img")

    def test_std_validation_blocks_via_validate_album_import(
        self, tmp_path: Path
    ) -> None:
        album = tmp_path / "album"
        _setup_std_staging(album, "nelu", orig=["a.jpg", "a.heic"])  # dup stems
        validation = validate_album_import(album, [])
        assert not validation.success
        assert any("std:nelu" in e for e in validation.errors)
