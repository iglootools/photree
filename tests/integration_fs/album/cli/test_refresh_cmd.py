from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from tests.fakes import invoke_cli
from tests.testkit import write_file


def _setup_album(album_dir: Path, *, images: bool = True) -> None:
    """
    Create a minimal album with archive, browsable, and JPEG dirs in sync.

    With images, face detection has work to do — and fails on the fake media,
    which the refresh now reports. Tests about other steps use videos only.
    """
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    write_file(album_dir / "ios-main" / "orig-vid" / "IMG_0115.MOV")
    write_file(album_dir / "main-vid" / "IMG_0115.MOV")
    if images:
        write_file(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
        write_file(album_dir / "ios-main" / "orig-img" / "IMG_0411.HEIC")
        write_file(album_dir / "main-img" / "IMG_0410.HEIC")
        write_file(album_dir / "main-img" / "IMG_0411.HEIC")
        write_file(album_dir / "main-jpg" / "IMG_0410.jpg")
        write_file(album_dir / "main-jpg" / "IMG_0411.jpg")


class TestAlbumRefresh:
    def test_creates_media_ids(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album, images=False)

        result = invoke_cli(["album", "refresh", "-a", str(album)])

        assert result.exit_code == 0
        assert load_media_metadata(album) is not None

    def test_dry_run(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album)

        result = invoke_cli(["album", "refresh", "-a", str(album), "--dry-run"])

        assert result.exit_code == 0
        assert load_media_metadata(album) is None

    def test_dry_run_labels_summary_line(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album, images=False)

        result = invoke_cli(["album", "refresh", "-a", str(album), "-n"])

        assert result.exit_code == 0
        assert "[dry-run] ✓ album refresh planned" in result.output

    def test_idempotent(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album, images=False)

        invoke_cli(["album", "refresh", "-a", str(album)])
        result = invoke_cli(["album", "refresh", "-a", str(album)])

        assert result.exit_code == 0

    def test_face_detection_failures_are_reported(self, tmp_path: Path) -> None:
        """Regression: face failures used to be dropped and the refresh exit 0."""
        album = tmp_path / "album"
        _setup_album(album)

        result = invoke_cli(["album", "refresh", "-a", str(album)])

        assert result.exit_code == 1
        assert "face detection failed for 2 image(s)" in result.output
        assert "main/0410 (thumbnail)" in result.output
        assert "photree album detect-faces --album-dir" in result.output
        # The other steps still ran
        assert load_media_metadata(album) is not None


class TestAlbumRefreshOfANonAlbum:
    def test_directory_without_album_or_media_source_is_refused(
        self,
        tmp_path: Path,
    ) -> None:
        not_album = tmp_path / "gallery root"
        write_file(not_album / "notes.txt")

        result = invoke_cli(["album", "refresh", "-a", str(not_album)])

        assert result.exit_code == 1
        assert "Not an album" in result.output
        assert "photree album init --album-dir" in result.output
        assert sorted(p.name for p in not_album.iterdir()) == ["notes.txt"]

    def test_media_source_without_album_yaml_is_refreshed(
        self,
        tmp_path: Path,
    ) -> None:
        album = tmp_path / "album"
        write_file(album / "ios-main" / "orig-vid" / "IMG_0115.MOV")

        result = invoke_cli(["album", "refresh", "-a", str(album)])

        assert result.exit_code == 0, result.output
        assert load_media_metadata(album) is not None
