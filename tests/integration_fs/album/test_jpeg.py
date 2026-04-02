"""Tests for photree.album.jpeg module."""

from pathlib import Path

from photree.album.jpeg import (
    RefreshResult,
    convert_single_file,
    noop_convert_single,
    refresh_jpeg_dir,
)


def _fake_convert(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Test converter that creates a .jpg file by copying (no sips needed)."""
    ext = src.suffix.lower()
    if ext == ".heic":
        dst = dst_dir / Path(src.name).with_suffix(".jpg").name
        if not dry_run:
            dst.write_text(src.read_text())
        return dst
    elif ext in {".jpg", ".jpeg"}:
        dst = dst_dir / src.name
        if not dry_run:
            dst.write_text(src.read_text())
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

        refresh_jpeg_dir(
            src_dir,
            dst_dir,
            convert_file=_fake_convert,
            on_file_start=lambda f: started.append(f),
            on_file_end=lambda f, s: ended.append((f, s)),
        )

        assert started == ["IMG_0001.HEIC"]
        assert ended == [("IMG_0001.HEIC", True)]
