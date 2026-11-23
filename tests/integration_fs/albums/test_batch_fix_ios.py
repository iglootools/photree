from pathlib import Path

from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.cmd_handler.fix_ios import batch_fix_ios
from photree.cli import app
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from tests.fakes import ALL_DEPS_RUNTIME

runner = CliRunner()


def _files(album: Path, subdir: str, *names: str) -> None:
    directory = album / "ios-main" / subdir
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text(f"data-{name}", encoding="utf-8")


def _names(album: Path, subdir: str) -> set[str]:
    return {f.name for f in (album / "ios-main" / subdir).iterdir()}


def _fixable_album(base: Path) -> Path:
    """Create an album with an edited image in orig-img and an orphan sidecar."""
    album = base / "2024-07-14 - Fixable"
    _files(album, "orig-img", "IMG_0001.HEIC", "IMG_E0001.HEIC", "IMG_9999.AAE")
    _files(album, "edit-img")
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    return album


def _conflicting_album(base: Path) -> Path:
    """Create an album whose miscategorized image would overwrite one in edit-img."""
    album = base / "2024-07-15 - Conflict"
    _files(album, "orig-img", "IMG_0002.HEIC", "IMG_E0002.HEIC")
    _files(album, "edit-img", "IMG_E0002.HEIC")
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    return album


class TestBatchFixIos:
    def test_flags_reach_each_album_and_a_failure_is_captured(
        self,
        tmp_path: Path,
    ) -> None:
        fixable = _fixable_album(tmp_path)
        conflicting = _conflicting_album(tmp_path)

        result = batch_fix_ios(
            [conflicting, fixable],
            rm_orphan_sidecar=True,
            mv_miscategorized=True,
        )

        assert result.fixed == 1
        assert [f.album_dir for f in result.failures] == [conflicting]
        assert "IMG_E0002.HEIC" in result.failures[0].reason
        # --mv-miscategorized and --rm-orphan-sidecar both reached the album.
        assert _names(fixable, "orig-img") == {"IMG_0001.HEIC"}
        assert _names(fixable, "edit-img") == {"IMG_E0001.HEIC"}
        # The failing album is left as it was.
        assert _names(conflicting, "orig-img") == {"IMG_0002.HEIC", "IMG_E0002.HEIC"}

    def test_rm_miscategorized_deletes_instead_of_moving(self, tmp_path: Path) -> None:
        fixable = _fixable_album(tmp_path)

        result = batch_fix_ios([fixable], rm_miscategorized=True)

        assert result.failures == ()
        assert _names(fixable, "orig-img") == {"IMG_0001.HEIC", "IMG_9999.AAE"}
        assert _names(fixable, "edit-img") == set()

    def test_dry_run_changes_nothing(self, tmp_path: Path) -> None:
        fixable = _fixable_album(tmp_path)

        result = batch_fix_ios(
            [fixable],
            dry_run=True,
            rm_orphan_sidecar=True,
            mv_miscategorized=True,
        )

        assert result.fixed == 1
        assert _names(fixable, "orig-img") == {
            "IMG_0001.HEIC",
            "IMG_E0001.HEIC",
            "IMG_9999.AAE",
        }


class TestFixIosCommands:
    def test_albums_fix_ios_fixes_and_reports_a_retry_with_its_flags(
        self,
        tmp_path: Path,
    ) -> None:
        fixable = _fixable_album(tmp_path)
        _conflicting_album(tmp_path)

        result = runner.invoke(
            app,
            ["albums", "fix-ios", "-d", str(tmp_path), "--mv-miscategorized"],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 1
        assert _names(fixable, "edit-img") == {"IMG_E0001.HEIC"}
        assert '2024-07-15 - Conflict" --mv-miscategorized' in result.output

    def test_gallery_fix_ios_fixes_the_gallery_albums(self, tmp_path: Path) -> None:
        gallery = tmp_path / "gallery"
        gallery.mkdir()
        save_gallery_metadata(gallery, GalleryMetadata(faces_enabled=False))
        fixable = _fixable_album(gallery / "albums" / "2024")

        result = runner.invoke(
            app,
            ["gallery", "fix-ios", "-g", str(gallery), "--rm-orphan-sidecar"],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 0, result.output
        assert _names(fixable, "orig-img") == {"IMG_0001.HEIC", "IMG_E0001.HEIC"}
