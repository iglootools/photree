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

from photree.album.cli.runtime import AlbumRuntime
from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.id import generate_album_id
from photree.album.refresh import (
    AlbumRefreshResult,
    RefreshFn,
    refresh_album_derived_data,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.common.exif import ExifTagReader
from photree.common.sysdeps import SystemDependency
from photree.foundation.linking import LinkMode
from tests.fakes import copy_convert_single, fake_album_runtime, invoke_cli
from tests.testkit import make_gallery, write_file


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
    write_file(d / "ios-main/orig-img/IMG_0001.HEIC")
    if album_id is not None:
        save_album_metadata(d, AlbumMetadata(id=album_id))
    return d


def _place_gallery_album(gallery: Path, name: str, *, album_id: str) -> Path:
    target = gallery / "albums" / name[:4] / name
    write_file(target / "ios-main/orig-img/IMG_0001.HEIC")
    save_album_metadata(target, AlbumMetadata(id=album_id))
    return target


class TestValidationGate:
    def test_collision_aborts_batch(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Morning")
        _make_source(base, "2024-07-14 - Evening")

        result = invoke_cli(
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
        )

        assert result.exit_code == 1
        assert "date collision on 2024-07-14" in result.output
        assert not (gallery / "albums").exists()

    def test_bad_name_aborts(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        source = _make_source(tmp_path / "src", "not-an-album-name")

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
        )

        assert result.exit_code == 1
        assert "not-an-album-name — naming:" in result.output
        assert not (gallery / "albums").exists()


class TestSkip:
    def test_already_imported_is_skipped(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _place_gallery_album(
            gallery,
            "2024-07-14 - Hiking",
            album_id=generate_album_id(),
        )
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
        )

        assert result.exit_code == 0
        assert "reimport" in result.output.lower()


class TestClobberGuard:
    def test_different_album_same_name_refused(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
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

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery), "--reimport"],
        )

        assert result.exit_code == 1
        assert "a different album already occupies" in result.output
        assert "Rename the source album before importing." in result.output


class TestInterruptedReimport:
    def test_hidden_album_aborts_with_the_name_to_restore(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        album_id = generate_album_id()
        album = _place_gallery_album(
            gallery,
            "2024-07-14 - Hiking",
            album_id=album_id,
        )
        album.rename(album.with_name(f".{album.name}.old"))
        source = _make_source(
            tmp_path / "src",
            "2024-07-14 - Hiking",
            album_id=album_id,
        )

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery), "--reimport"],
        )

        assert result.exit_code == 1
        assert "an interrupted reimport left this album hidden" in result.output
        assert f"Rename it back to {album}" in result.output
        assert not album.exists()


class TestDryRun:
    def test_dry_run_imports_nothing(self, tmp_path: Path) -> None:
        # No face-model stubbing needed: the analyzer factory is injected
        # lazily and dry-run never reaches face detection.
        gallery = make_gallery(tmp_path, faces_enabled=False)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery), "--dry-run"],
        )

        assert result.exit_code == 0
        assert "[dry-run] 1 album(s) would be imported, 0 failed." in result.output
        assert not (gallery / "albums" / "2024" / "2024-07-14 - Hiking").exists()


class TestImport:
    def test_imports_and_checks_the_album(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        assert (target / "main-img" / "IMG_0001.HEIC").is_file()
        assert "Album ID: " in result.output
        assert "Post-Import Check:" in result.output

    def test_incomplete_derived_data_fails(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_refresh_with_face_failure),
        )

        assert result.exit_code == 1
        assert "derived data is incomplete" in result.output
        assert "model exploded" in result.output
        assert (gallery / "albums" / "2024" / "2024-07-14 - Hiking").is_dir()

    def test_incomplete_derived_data_still_clusters_faces(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the command exited before clustering the placed album."""
        gallery = make_gallery(tmp_path)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_refresh_with_face_failure),
        )

        assert result.exit_code == 1
        assert "face clustering" in result.output

    def test_failed_post_import_check_fails(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import", "-a", str(source), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_skipped_refresh),
        )

        assert result.exit_code == 1
        assert "To investigate, run 'photree album check --album-dir" in result.output

    def test_link_mode_override_passes_the_post_import_check(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the check expected the gallery's link mode, not the override."""
        gallery = make_gallery(
            tmp_path,
            link_mode=LinkMode.HARDLINK,
            faces_enabled=False,
        )
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = invoke_cli(
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
            runtime=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        main_img = target / "main-img" / "IMG_0001.HEIC"
        assert not main_img.samefile(target / "ios-main" / "orig-img" / "IMG_0001.HEIC")


class TestImportAll:
    def test_imports_and_checks_every_album(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")
        _make_source(base, "2024-07-15 - Beach")

        result = invoke_cli(
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        assert "Done. 2 album(s) imported, 0 failed." in result.output

    def test_incomplete_derived_data_still_clusters_faces(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: with no album imported cleanly, clustering was skipped."""
        gallery = make_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_refresh_with_face_failure),
        )

        assert result.exit_code == 1
        assert "face clustering" in result.output
        assert "Post-Import Check:" not in result.output
        assert "0 album(s) imported, 1 failed." in result.output

    def test_failed_post_import_check_fails_the_run(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = invoke_cli(
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery)],
            runtime=_runtime_refreshing_with(_skipped_refresh),
        )

        assert result.exit_code == 1
        assert "1 failed post-import check" in result.output
        assert "To investigate failures, run:" in result.output

    def test_link_mode_override_passes_the_post_import_check(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: the batch check expected the gallery's link mode too."""
        gallery = make_gallery(
            tmp_path,
            link_mode=LinkMode.HARDLINK,
            faces_enabled=False,
        )
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = invoke_cli(
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
            runtime=_runtime_refreshing_with(_copy_refresh),
        )

        assert result.exit_code == 0, result.output
        assert "Done. 1 album(s) imported, 0 failed." in result.output
