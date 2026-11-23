"""
CLI tests for ``gallery import`` / ``gallery import-all``.

These cover the fast control-flow paths (validation gate, skip, clobber,
dry-run) that exit before any real media conversion or face-model loading.
The imports themselves run with a fake derived-data refresh (``_copy_refresh``
copies instead of converting and skips face detection), so neither ``sips``
nor the face model is needed; the importer's own stages are covered at the
function level in ``test_importer.py`` / ``test_reimport.py``.
"""

from pathlib import Path

from typer.testing import CliRunner

from photree.album.cli.runtime import AlbumRuntime
from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.id import generate_album_id
from photree.album.jpeg import copy_convert_single
from photree.album.refresh import (
    AlbumRefreshResult,
    RefreshFn,
    refresh_album_derived_data,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.common.exif import ExifTagReader
from photree.common.sysdeps import SystemDependency
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.linking import LinkMode
from tests.fakes import ALL_DEPS_RUNTIME, fake_album_runtime

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_gallery(
    tmp_path: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(
        gallery,
        GalleryMetadata(link_mode=link_mode, faces_enabled=False),
    )
    return gallery


def _copy_refresh(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    max_workers: int | None,
    exiftool: ExifTagReader | None,
    dry_run: bool,
    **_converter_and_faces: object,
) -> AlbumRefreshResult:
    """Run the real refresh, copying images instead of converting, with no faces."""
    return refresh_album_derived_data(
        album_dir,
        link_mode=link_mode,
        max_workers=max_workers,
        exiftool=exiftool,
        convert_file=copy_convert_single,
        dry_run=dry_run,
    )


def _refresh_with_face_failure(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    max_workers: int | None,
    exiftool: ExifTagReader | None,
    dry_run: bool,
    **_converter_and_faces: object,
) -> AlbumRefreshResult:
    """Refresh as :func:`_copy_refresh` does, then report a failed face detection."""
    _copy_refresh(
        album_dir,
        link_mode=link_mode,
        max_workers=max_workers,
        exiftool=exiftool,
        dry_run=dry_run,
    )
    return AlbumRefreshResult(
        face_failures=(
            ("main", FaceFailure("0001", FaceFailureStage.DETECTION, "model exploded")),
        ),
    )


def _skipped_refresh(*_: object, **__: object) -> AlbumRefreshResult:
    """Build no derived data, so the post-import check finds none."""
    return AlbumRefreshResult()


def _runtime_refreshing_with(refresh: RefreshFn) -> AlbumRuntime:
    """Every dependency installed, and *refresh* in place of the real one."""
    return fake_album_runtime(*SystemDependency, refresh=refresh)


def _make_source(base: Path, name: str, *, album_id: str | None = None) -> Path:
    d = base / name
    _write(d / "ios-main/orig-img/IMG_0001.HEIC")
    if album_id is not None:
        save_album_metadata(d, AlbumMetadata(id=album_id))
    return d


def _place_gallery_album(gallery: Path, name: str, *, album_id: str) -> Path:
    target = gallery / "albums" / name[:4] / name
    _write(target / "ios-main/orig-img/IMG_0001.HEIC")
    save_album_metadata(target, AlbumMetadata(id=album_id))
    return target


class TestValidationGate:
    def test_collision_aborts_batch(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Morning")
        _make_source(base, "2024-07-14 - Evening")

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 1
        assert "date collision on 2024-07-14" in result.output
        assert not (gallery / "albums").exists()

    def test_bad_name_aborts(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        source = _make_source(tmp_path / "src", "not-an-album-name")

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 1
        assert "not-an-album-name — naming:" in result.output
        assert not (gallery / "albums").exists()


class TestSkip:
    def test_already_imported_is_skipped(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _place_gallery_album(
            gallery,
            "2024-07-14 - Hiking",
            album_id=generate_album_id(),
        )
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 0
        assert "reimport" in result.output.lower()


class TestClobberGuard:
    def test_different_album_same_name_refused(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _place_gallery_album(
            gallery,
            "2024-07-14 - Hiking",
            album_id=generate_album_id(),
        )
        # Source carries a *different* ID than the gallery occupant.
        source = _make_source(
            tmp_path / "src",
            "2024-07-14 - Hiking",
            album_id=generate_album_id(),
        )

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery), "--reimport"],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 1
        assert "a different album already occupies" in result.output
        assert "Rename the source album before importing." in result.output


class TestDryRun:
    def test_dry_run_imports_nothing(self, tmp_path: Path) -> None:
        # No face-model stubbing needed: the analyzer factory is injected
        # lazily and dry-run never reaches face detection.
        gallery = _setup_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery), "--dry-run"],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 0
        assert "[dry-run] 1 album(s) would be imported, 0 failed." in result.output
        assert not (gallery / "albums" / "2024" / "2024-07-14 - Hiking").exists()


class TestImport:
    def test_imports_and_checks_the_album(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            obj=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        assert (target / "main-img" / "IMG_0001.HEIC").is_file()
        assert "Album ID: " in result.output
        assert "Post-Import Check:" in result.output

    def test_incomplete_derived_data_fails(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            obj=_runtime_refreshing_with(_refresh_with_face_failure),
        )

        assert result.exit_code == 1
        assert "derived data is incomplete" in result.output
        assert "model exploded" in result.output
        assert (gallery / "albums" / "2024" / "2024-07-14 - Hiking").is_dir()

    def test_failed_post_import_check_fails(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            obj=_runtime_refreshing_with(_skipped_refresh),
        )

        assert result.exit_code == 1
        assert "To investigate, run 'photree album check --album-dir" in result.output

    def test_link_mode_override_passes_the_post_import_check(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the check expected the gallery's link mode, not the override."""
        gallery = _setup_gallery(tmp_path, LinkMode.HARDLINK)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            [
                "gallery",
                "import",
                "-a",
                str(source),
                "-g",
                str(gallery),
                "--link-mode",
                "copy",
            ],
            obj=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        main_img = target / "main-img" / "IMG_0001.HEIC"
        assert not main_img.samefile(target / "ios-main" / "orig-img" / "IMG_0001.HEIC")


class TestImportAll:
    def test_imports_and_checks_every_album(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")
        _make_source(base, "2024-07-15 - Beach")

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
            obj=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        assert "Done. 2 album(s) imported, 0 failed." in result.output

    def test_failed_post_import_check_fails_the_run(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
            obj=_runtime_refreshing_with(_skipped_refresh),
        )

        assert result.exit_code == 1
        assert "1 failed post-import check" in result.output
        assert "To investigate failures, run:" in result.output

    def test_link_mode_override_passes_the_post_import_check(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the batch check expected the gallery's link mode too."""
        gallery = _setup_gallery(tmp_path, LinkMode.HARDLINK)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            [
                "gallery",
                "import-all",
                "-d",
                str(base),
                "-g",
                str(gallery),
                "--link-mode",
                "copy",
            ],
            obj=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        assert "Done. 1 album(s) imported, 0 failed." in result.output
