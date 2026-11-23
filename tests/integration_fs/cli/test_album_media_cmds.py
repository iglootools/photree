"""The ``album rm-media``, ``mv-media`` and ``list-media`` commands, end to end."""

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app

runner = CliRunner()


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"data-{path.name}", encoding="utf-8")


def _album(path: Path, files: list[str]) -> Path:
    path.mkdir(parents=True)
    save_album_metadata(path, AlbumMetadata(id=generate_album_id()))
    for rel in files:
        _write(path / rel)
    return path


class TestMvMedia:
    def test_type_mismatch_is_refused_with_its_reason(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        src = _album(tmp_path / "src", ["ios-main/orig-img/IMG_0001.HEIC"])
        _album(tmp_path / "dst", ["std-main/orig-img/beach.jpg"])
        chdir(tmp_path)

        result = runner.invoke(
            app,
            [
                "album",
                "mv-media",
                "--source-album",
                "src",
                "--dest-album",
                "dst",
                "ios-main/orig-img/IMG_0001.HEIC",
            ],
        )

        assert result.exit_code == 1
        assert "dst has media source(s) main of the other type" in result.output
        assert (src / "ios-main/orig-img/IMG_0001.HEIC").exists()
