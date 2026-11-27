"""The ``album rm-media``, ``mv-media`` and ``list-media`` commands, end to end."""

import csv
import io
from collections.abc import Callable
from pathlib import Path

from photree.album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
    generate_album_id,
    generate_media_id,
)
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    save_media_metadata,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from tests.fakes import invoke_cli
from tests.testkit import write_file


def _album(path: Path, files: list[str]) -> Path:
    path.mkdir(parents=True)
    save_album_metadata(path, AlbumMetadata(id=generate_album_id()))
    for rel in files:
        write_file(path / rel, f"data-{Path(rel).name}")
    return path


def _ios_image(number: str) -> list[str]:
    return [
        f"ios-main/orig-img/IMG_{number}.HEIC",
        f"main-img/IMG_{number}.HEIC",
        f"main-jpg/IMG_{number}.jpg",
    ]


class TestRmMedia:
    def test_removes_every_variant_and_suggests_a_check(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        album = _album(tmp_path / "trip", [*_ios_image("0001"), *_ios_image("0002")])
        chdir(tmp_path)

        result = invoke_cli(
            ["album", "rm-media", "--album-dir", "trip", "main-jpg/IMG_0001.jpg"],
        )

        assert result.exit_code == 0, result.output
        assert "Done. Removed 3 file(s):" in result.output
        assert 'photree album check --album-dir "trip"' in result.output
        assert not (album / "ios-main/orig-img/IMG_0001.HEIC").exists()
        assert not (album / "main-jpg/IMG_0001.jpg").exists()
        assert (album / "ios-main/orig-img/IMG_0002.HEIC").exists()

    def test_dry_run_reports_without_removing(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "trip", _ios_image("0001"))

        result = invoke_cli(
            [
                "album",
                "rm-media",
                "--dry-run",
                "--album-dir",
                str(album),
                "main-jpg/IMG_0001.jpg",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Would remove 3 file(s):" in result.output
        assert (album / "ios-main/orig-img/IMG_0001.HEIC").exists()


class TestMvMedia:
    def test_moves_every_variant_and_suggests_checks(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        src = _album(tmp_path / "src", _ios_image("0001"))
        dst = _album(tmp_path / "dst", [])
        chdir(tmp_path)

        result = invoke_cli(
            [
                "album",
                "mv-media",
                "--source-album",
                "src",
                "--dest-album",
                "dst",
                "main-jpg/IMG_0001.jpg",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Done. Moved 3 file(s):" in result.output
        assert 'photree album check --album-dir "src"' in result.output
        assert 'photree album check --album-dir "dst"' in result.output
        assert not (src / "ios-main").exists()
        assert (dst / "ios-main/orig-img/IMG_0001.HEIC").exists()
        assert (dst / "main-jpg/IMG_0001.jpg").exists()

    def test_conflicts_are_listed_up_to_ten(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        numbers = [f"{n:04d}" for n in range(1, 13)]
        files = [f for number in numbers for f in _ios_image(number)]
        src = _album(tmp_path / "src", files)
        _album(tmp_path / "dst", files)
        chdir(tmp_path)

        result = invoke_cli(
            [
                "album",
                "mv-media",
                "--source-album",
                "src",
                "--dest-album",
                "dst",
                *(f"main-jpg/IMG_{number}.jpg" for number in numbers),
            ],
        )

        assert result.exit_code == 1
        assert "Move would conflict with 36 existing file(s) in dst:" in (result.output)
        assert "... and 26 more" in result.output
        listed = [line for line in result.output.splitlines() if line.startswith("  ")]
        assert len(listed) == 11
        assert (src / "ios-main/orig-img/IMG_0001.HEIC").exists()

    def test_type_mismatch_is_refused_with_its_reason(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        src = _album(tmp_path / "src", ["ios-main/orig-img/IMG_0001.HEIC"])
        _album(tmp_path / "dst", ["std-main/orig-img/beach.jpg"])
        chdir(tmp_path)

        result = invoke_cli(
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


def _album_with_ids(path: Path) -> tuple[Path, str, str, str]:
    """Create an album with one image and one video ID; return it and the IDs."""
    album_id = generate_album_id()
    image_id = generate_media_id()
    video_id = generate_media_id()
    path.mkdir(parents=True)
    save_album_metadata(path, AlbumMetadata(id=album_id))
    save_media_metadata(
        path,
        MediaMetadata(
            media_sources={
                "main": MediaSourceMediaMetadata(
                    images={image_id: "0001"},
                    videos={video_id: "0002"},
                ),
            },
        ),
    )
    return path, album_id, image_id, video_id


class TestListMedia:
    def test_text_lists_ids_by_media_source(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        _, album_id, image_id, video_id = _album_with_ids(tmp_path / "trip")
        chdir(tmp_path)

        result = invoke_cli(["album", "list-media", "--album-dir", "trip"])

        assert result.exit_code == 0, result.output
        assert result.output.splitlines() == [
            "Album: trip",
            f"  id: {format_album_external_id(album_id)}",
            "  main:",
            "    images:",
            f"      {format_image_external_id(image_id)}: 0001",
            "    videos:",
            f"      {format_video_external_id(video_id)}: 0002",
        ]

    def test_csv_has_the_header_scripts_read(self, tmp_path: Path) -> None:
        album, album_id, image_id, video_id = _album_with_ids(tmp_path / "trip")

        result = invoke_cli(
            ["album", "list-media", "--album-dir", str(album), "--output", "csv"],
        )

        assert result.exit_code == 0, result.output
        album_ext_id = format_album_external_id(album_id)
        assert list(csv.reader(io.StringIO(result.stdout))) == [
            ["album_id", "media_source", "type", "id", "key"],
            [album_ext_id, "main", "image", format_image_external_id(image_id), "0001"],
            [album_ext_id, "main", "video", format_video_external_id(video_id), "0002"],
        ]
