import shutil
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from photree.album.id import generate_album_id
from photree.album.refresh import refresh_album_derived_data
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.clihelpers.runtime import Runtime
from photree.common.exif import exiftool_session, set_exif_date_time
from photree.common.sysdeps import SystemDependency
from photree.foundation.linking import LinkMode
from tests.fakes import fake_runtime, invoke_cli
from tests.testkit import make_album, mark_album, write_file

requires_exiftool = pytest.mark.skipif(
    not shutil.which("exiftool"),
    reason="exiftool not installed",
)


def _real_exiftool_runtime() -> Runtime:
    """Every dependency present; exiftool is the real one, since the check runs it."""
    fake_which = fake_runtime(*SystemDependency).which

    def which(name: str) -> str | None:
        return shutil.which(name) if name == "exiftool" else fake_which(name)

    return replace(fake_runtime(*SystemDependency), which=which)


def _album_with_exif_mismatch(tmp_path: Path) -> Path:
    """Build a std album dated 2024-07-20 holding a picture taken on 2023-01-01."""
    album = tmp_path / "2024-07-20 - Beach"
    img = album / "std-main" / "orig-img" / "DSC_0001.jpg"
    img.parent.mkdir(parents=True)
    cv2.imwrite(str(img), np.zeros((8, 8, 3), dtype=np.uint8))
    set_exif_date_time([img], "2023-01-01T10:00:00")
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    # Not `album refresh`, whose face detection needs sips for its thumbnails.
    with exiftool_session() as exiftool:
        refresh_album_derived_data(
            album,
            link_mode=LinkMode.HARDLINK,
            exiftool=exiftool,
        )
    return album


@requires_exiftool
class TestAlbumCheckExifDateMismatch:
    def test_mismatch_fails_the_check_by_default(self, tmp_path: Path) -> None:
        runtime = _real_exiftool_runtime()
        album = _album_with_exif_mismatch(tmp_path)

        result = invoke_cli(
            ["album", "check", "--album-dir", str(album)],
            runtime=runtime,
        )

        assert result.exit_code == 1, result.output
        assert "Failed due to fatal warning flags:" in result.output
        assert "DSC_0001.jpg  2023-01-01T10:00:00" in result.output

    def test_mismatch_is_only_a_warning_without_the_fatal_flag(
        self,
        tmp_path: Path,
    ) -> None:
        runtime = _real_exiftool_runtime()
        album = _album_with_exif_mismatch(tmp_path)

        result = invoke_cli(
            ["album", "check", "--album-dir", str(album), "--no-fatal-exif-date-match"],
            runtime=runtime,
        )

        assert result.exit_code == 0, result.output
        assert "exif: 1 file(s) outside album date (2024-07-20)" in result.output
        assert "Failed due to fatal warning flags:" not in result.output


def _passing_std_album(parent: Path, name: str) -> Path:
    """Build a std album that passes every check (no EXIF cache, no faces)."""
    album = parent / name
    write_file(album / "std-main" / "orig-img" / "DSC_0001.jpg")
    mark_album(album)
    refresh_album_derived_data(album, link_mode=LinkMode.HARDLINK, exiftool=None)
    return album


class TestAlbumCheckSiblingDateCollision:
    _ARGS = ("--no-check-exif-date-match",)

    def test_album_passes_without_a_sibling_on_its_date(self, tmp_path: Path) -> None:
        album = _passing_std_album(tmp_path, "2024-07-14 - Hike")

        result = invoke_cli(["album", "check", "-a", str(album), *self._ARGS])

        assert result.exit_code == 0, result.output

    def test_a_sibling_on_the_same_date_fails_the_check(self, tmp_path: Path) -> None:
        album = _passing_std_album(tmp_path, "2024-07-14 - Hike")
        make_album(tmp_path, "2024-07-14 - Swim")

        result = invoke_cli(["album", "check", "-a", str(album), *self._ARGS])

        assert result.exit_code == 1, result.output
        assert "date collisions: 1 date(s)" in result.output

    def test_no_check_date_part_collision_ignores_the_sibling(
        self,
        tmp_path: Path,
    ) -> None:
        album = _passing_std_album(tmp_path, "2024-07-14 - Hike")
        make_album(tmp_path, "2024-07-14 - Swim")

        result = invoke_cli(
            [
                "album",
                "check",
                "-a",
                str(album),
                *self._ARGS,
                "--no-check-date-part-collision",
            ],
        )

        assert result.exit_code == 0, result.output
