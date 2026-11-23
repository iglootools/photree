from pathlib import Path

from photree.album.exif_date_check import check_exif_date_match
from tests.fakes import FakeExifTool

_ON_DATE = "2024:07:14 10:00:00"
_OFF_DATE = "2023:01:01 10:00:00"


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _std_album(album: Path) -> None:
    _write(album / "std-main" / "orig-img" / "DSC_0001.HEIC")
    _write(album / "std-main" / "edit-img" / "DSC_0001.HEIC")
    _write(album / "std-main" / "orig-vid" / "VID_0002.MOV")
    _write(album / "main-img" / "DSC_0001.HEIC")
    _write(album / "main-jpg" / "DSC_0001.jpg")
    _write(album / "main-vid" / "VID_0002.MOV")


class TestUpstreamFiles:
    def test_std_image_upstream_is_the_archive(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool(
                {"DSC_0001.jpg": _OFF_DATE, "VID_0002.MOV": _ON_DATE},
            ),
        )

        assert check is not None
        (mismatch,) = check.mismatches
        assert mismatch.file_name == "main-jpg/DSC_0001.jpg"
        assert mismatch.upstream_files == (
            "std-main/orig-img/DSC_0001.HEIC",
            "std-main/edit-img/DSC_0001.HEIC",
        )
        assert not mismatch.is_ios

    def test_std_video_upstream_is_the_archive(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool(
                {"DSC_0001.jpg": _ON_DATE, "VID_0002.MOV": _OFF_DATE},
            ),
        )

        assert check is not None
        (mismatch,) = check.mismatches
        assert mismatch.file_name == "main-vid/VID_0002.MOV"
        assert mismatch.upstream_files == ("std-main/orig-vid/VID_0002.MOV",)
