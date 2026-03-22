"""Tests for the image-capture-all batch import."""

from pathlib import Path

from photree.fsprotocol import SELECTION_DIR
from photree.importer.image_capture_all import (
    categorize_albums,
    run_batch_import,
    scan_albums,
    validate_albums,
)


def _noop_convert(_src: Path, _dst_dir: Path, *, dry_run: bool) -> Path | None:
    """No-op converter for tests (avoids calling sips on fake HEIC files)."""
    return None


def _setup_image_capture_dir(tmp_path: Path, filenames: list[str]) -> Path:
    """Create a fake Image Capture directory with the given filenames."""
    ic_dir = tmp_path / "image_capture"
    ic_dir.mkdir(exist_ok=True)
    for name in filenames:
        (ic_dir / name).write_text("data")
    return ic_dir


def _setup_album(parent: Path, album_name: str, selection_files: list[str]) -> Path:
    """Create an album with a to-import/ subfolder under parent."""
    album = parent / album_name
    selection = album / SELECTION_DIR
    selection.mkdir(parents=True)
    for name in selection_files:
        (selection / name).write_text("data")
    return album


class TestScanAlbums:
    def test_categorizes_albums(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        _setup_album(albums_dir, "has-files", ["IMG_0001.HEIC"])
        (albums_dir / "no-selection").mkdir()
        (albums_dir / "empty-selection" / SELECTION_DIR).mkdir(parents=True)

        scan = scan_albums(albums_dir)
        assert len(scan.to_import) == 1
        assert len(scan.no_selection) == 1
        assert len(scan.empty_selection) == 1


class TestCategorizeAlbums:
    def test_categorizes_explicit_dirs(self, tmp_path: Path) -> None:
        has_files = _setup_album(tmp_path, "has-files", ["IMG_0001.HEIC"])
        no_sel = tmp_path / "no-selection"
        no_sel.mkdir()
        empty_sel = tmp_path / "empty-selection"
        (empty_sel / SELECTION_DIR).mkdir(parents=True)

        scan = categorize_albums([has_files, no_sel, empty_sel])
        assert len(scan.to_import) == 1
        assert len(scan.no_selection) == 1
        assert len(scan.empty_selection) == 1


class TestValidateAlbums:
    def test_all_valid(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        _setup_album(albums_dir, "trip", ["IMG_0001.HEIC"])
        ic_files = ["IMG_0001.HEIC", "IMG_0001.AAE"]

        scan = scan_albums(albums_dir)
        validations = validate_albums(scan.to_import, ic_files)
        assert len(validations) == 1
        assert all(v.success for v in validations)

    def test_fails_when_selection_has_no_ic_match(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        _setup_album(albums_dir, "trip", ["IMG_9999.HEIC"])
        ic_files = ["IMG_0001.HEIC"]

        scan = scan_albums(albums_dir)
        validations = validate_albums(scan.to_import, ic_files)
        failed = [v for v in validations if not v.success]
        assert len(failed) == 1
        assert failed[0].album_dir.name == "trip"
        assert len(failed[0].errors) >= 1


class TestBatchImport:
    def test_imports_albums_with_selection_skips_others(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC", "IMG_0002.AAE"],
        )
        _setup_album(albums_dir, "trip-paris", ["IMG_0001.HEIC"])
        _setup_album(albums_dir, "trip-london", ["IMG_0002.HEIC"])
        (albums_dir / "empty-album").mkdir()
        (albums_dir / "no-photos" / SELECTION_DIR).mkdir(parents=True)

        result = run_batch_import(
            albums_dir=albums_dir, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert result.imported == 2
        assert result.skipped == 2
        assert (albums_dir / "trip-paris" / "ios/orig-img" / "IMG_0001.HEIC").exists()
        assert (albums_dir / "trip-london" / "ios/orig-img" / "IMG_0002.HEIC").exists()
        assert not (albums_dir / "empty-album" / "ios/orig-img").exists()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC", "IMG_0001.AAE"])
        _setup_album(albums_dir, "trip", ["IMG_0001.HEIC"])

        result = run_batch_import(
            albums_dir=albums_dir,
            image_capture_dir=ic_dir,
            dry_run=True,
            convert_file=_noop_convert,
        )

        assert result.imported == 1
        assert (albums_dir / "trip" / SELECTION_DIR).exists()
        assert not (albums_dir / "trip" / "ios/orig-img").exists()

    def test_empty_parent_dir(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC"])

        result = run_batch_import(
            albums_dir=albums_dir, image_capture_dir=ic_dir, convert_file=_noop_convert
        )

        assert result.imported == 0
        assert result.skipped == 0

    def test_imports_explicit_album_dirs(self, tmp_path: Path) -> None:
        ic_dir = _setup_image_capture_dir(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC", "IMG_0002.AAE"],
        )
        album_a = _setup_album(tmp_path, "trip-paris", ["IMG_0001.HEIC"])
        album_b = _setup_album(tmp_path, "trip-london", ["IMG_0002.HEIC"])

        result = run_batch_import(
            album_dirs=[album_a, album_b],
            image_capture_dir=ic_dir,
            convert_file=_noop_convert,
        )

        assert result.imported == 2
        assert result.skipped == 0
        assert (album_a / "ios/orig-img" / "IMG_0001.HEIC").exists()
        assert (album_b / "ios/orig-img" / "IMG_0002.HEIC").exists()

    def test_aborts_all_when_any_album_fails_validation(self, tmp_path: Path) -> None:
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        ic_dir = _setup_image_capture_dir(tmp_path, ["IMG_0001.HEIC", "IMG_0001.AAE"])
        _setup_album(albums_dir, "valid", ["IMG_0001.HEIC"])
        _setup_album(albums_dir, "invalid", ["IMG_9999.HEIC"])  # no IC match

        validation_errors: list[str] = []
        result = run_batch_import(
            albums_dir=albums_dir,
            image_capture_dir=ic_dir,
            on_validation_error=lambda name, errs: validation_errors.append(name),
            convert_file=_noop_convert,
        )

        assert result.imported == 0  # nothing imported
        assert len(validation_errors) == 1
        assert "invalid" in validation_errors
        # valid album should NOT have been processed either
        assert not (albums_dir / "valid" / "ios/orig-img").exists()
