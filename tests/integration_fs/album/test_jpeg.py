from pathlib import Path

import pytest

from photree.album.jpeg import (
    JpegAction,
    RefreshResult,
    convert_single_file,
    jpeg_action,
    jpeg_name,
    noop_convert_single,
    refresh_jpeg_dir,
)
from photree.common.sips import SipsError
from tests.testkit import file_names, write_file


def _fake_convert(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Test converter that creates a .jpg file by copying (no sips needed)."""
    ext = src.suffix.lower()
    if ext == ".heic":
        dst = dst_dir / Path(src.name).with_suffix(".jpg").name
        if not dry_run:
            dst.write_text(src.read_text(encoding="utf-8"))
        return dst
    elif ext in {".jpg", ".jpeg"}:
        dst = dst_dir / src.name
        if not dry_run:
            dst.write_text(src.read_text(encoding="utf-8"))
        return dst
    else:
        return None


class TestConvertSingleFile:
    def test_noop_returns_none(self, tmp_path: Path) -> None:
        src = tmp_path / "IMG_0001.HEIC"
        src.write_text("data")
        result = noop_convert_single(src, tmp_path, dry_run=False)
        assert result is None

    def test_copies_png(self, tmp_path: Path) -> None:
        src = tmp_path / "IMG_0001.PNG"
        src.write_text("data")
        dst_dir = tmp_path / "out"
        dst_dir.mkdir()
        result = convert_single_file(src, dst_dir, dry_run=False)
        assert result == dst_dir / "IMG_0001.PNG"
        assert (dst_dir / "IMG_0001.PNG").exists()


class TestRefreshJpegDir:
    def test_converts_heic_and_copies_jpeg(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "main-img"
        dst_dir = tmp_path / "main-jpg"
        src_dir.mkdir()
        (src_dir / "IMG_0001.HEIC").write_text("heic-data")
        (src_dir / "IMG_0002.JPG").write_text("jpeg-data")

        result = refresh_jpeg_dir(src_dir, dst_dir, convert_file=_fake_convert)

        assert result == RefreshResult(converted=1, copied=1, skipped=0)
        assert (dst_dir / "IMG_0001.jpg").exists()
        assert (dst_dir / "IMG_0002.JPG").exists()

    def test_skips_non_image_files(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "main-img"
        dst_dir = tmp_path / "main-jpg"
        src_dir.mkdir()
        (src_dir / "IMG_0001.PNG").write_text("png-data")

        result = refresh_jpeg_dir(src_dir, dst_dir, convert_file=_fake_convert)

        assert result == RefreshResult(converted=0, copied=0, skipped=1)

    def test_clears_dst_dir_before_converting(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "main-img"
        dst_dir = tmp_path / "main-jpg"
        src_dir.mkdir()
        dst_dir.mkdir()
        (dst_dir / "old-file.jpg").write_text("stale")
        (src_dir / "IMG_0001.HEIC").write_text("heic-data")

        refresh_jpeg_dir(src_dir, dst_dir, convert_file=_fake_convert)

        assert not (dst_dir / "old-file.jpg").exists()
        assert (dst_dir / "IMG_0001.jpg").exists()

    def test_missing_src_dir_returns_empty_result(self, tmp_path: Path) -> None:
        result = refresh_jpeg_dir(
            tmp_path / "nonexistent",
            tmp_path / "dst",
            convert_file=_fake_convert,
        )
        assert result == RefreshResult(converted=0, copied=0, skipped=0)

    def test_calls_on_file_callbacks(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "main-img"
        dst_dir = tmp_path / "main-jpg"
        src_dir.mkdir()
        (src_dir / "IMG_0001.HEIC").write_text("data")

        started: list[str] = []
        ended: list[tuple[str, bool]] = []

        def record_end(name: str, *, success: bool) -> None:
            ended.append((name, success))

        refresh_jpeg_dir(
            src_dir,
            dst_dir,
            convert_file=_fake_convert,
            on_file_start=started.append,
            on_file_end=record_end,
        )

        assert started == ["IMG_0001.HEIC"]
        assert ended == [("IMG_0001.HEIC", True)]


class TestJpegRefresh:
    def test_sips_error_on_sequential_path_is_recorded(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        write_file(src / "IMG_0001.HEIC")

        def failing_sips(s: Path, _d: Path, *, dry_run: bool) -> Path | None:  # noqa: ARG001 - ConvertFile's signature
            raise SipsError(path=s, returncode=1, stderr="not an image")

        result = refresh_jpeg_dir(src, dst, convert_file=failing_sips)

        assert [f.filename for f in result.failed] == ["IMG_0001.HEIC"]
        assert "not an image" in result.failed[0].reason

    @pytest.mark.parametrize("max_workers", [None, 4])
    def test_skipped_file_is_not_reported_as_failure(
        self,
        tmp_path: Path,
        max_workers: int | None,
    ) -> None:
        """Both paths report a deliberately skipped file the same way."""
        src, dst = tmp_path / "img", tmp_path / "jpg"
        write_file(src / "IMG_0001.HEIC")
        write_file(src / "IMG_0001.MOV")  # Live Photo video: no JPEG variant
        ends: list[tuple[str, bool]] = []

        def record_end(name: str, *, success: bool) -> None:
            ends.append((name, success))

        result = refresh_jpeg_dir(
            src,
            dst,
            convert_file=noop_convert_single,
            max_workers=max_workers,
            on_file_end=record_end,
        )

        assert result.success
        assert result.skipped == 2
        assert ends == [("IMG_0001.HEIC", True)]

    def test_parallel_path_uses_the_given_converter(self, tmp_path: Path) -> None:
        """Parallelism is chosen by max_workers alone, never by converter identity."""
        src, dst = tmp_path / "img", tmp_path / "jpg"
        write_file(src / "a.jpg")
        write_file(src / "b.jpg")
        calls: list[str] = []

        def recording(s: Path, d: Path, *, dry_run: bool) -> Path | None:  # noqa: ARG001 - ConvertFile's signature
            calls.append(s.name)
            return d / s.name

        result = refresh_jpeg_dir(src, dst, convert_file=recording, max_workers=4)

        assert sorted(calls) == ["a.jpg", "b.jpg"]
        assert result.copied == 2

    @pytest.mark.parametrize("src_exists", [True, False])
    def test_stale_jpegs_cleared_when_source_empty(
        self,
        tmp_path: Path,
        *,
        src_exists: bool,
    ) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        if src_exists:
            src.mkdir()
        write_file(dst / "stale.jpg")

        refresh_jpeg_dir(src, dst)

        assert file_names(dst) == set()

    def test_classification(self) -> None:
        assert jpeg_action("IMG_0001.HEIC") == JpegAction.CONVERT
        assert jpeg_action("IMG_0001.png") == JpegAction.COPY
        assert jpeg_action("IMG_0001.MOV") == JpegAction.SKIP
        assert jpeg_name("IMG_0001.DNG") == "IMG_0001.jpg"
        assert jpeg_name("IMG_0001.png") == "IMG_0001.png"
        assert jpeg_name("IMG_0001.MOV") is None
