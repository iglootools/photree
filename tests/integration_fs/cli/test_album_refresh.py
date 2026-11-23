from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from tests.fakes import invoke_cli


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_album(album_dir: Path, *, images: bool = True) -> None:
    """
    Create a minimal album with archive, browsable, and JPEG dirs in sync.

    With images, face detection has work to do — and fails on the fake media,
    which the refresh now reports. Tests about other steps use videos only.
    """
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    _write(album_dir / "ios-main" / "orig-vid" / "IMG_0115.MOV")
    _write(album_dir / "main-vid" / "IMG_0115.MOV")
    if images:
        _write(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
        _write(album_dir / "ios-main" / "orig-img" / "IMG_0411.HEIC")
        _write(album_dir / "main-img" / "IMG_0410.HEIC")
        _write(album_dir / "main-img" / "IMG_0411.HEIC")
        _write(album_dir / "main-jpg" / "IMG_0410.jpg")
        _write(album_dir / "main-jpg" / "IMG_0411.jpg")


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
