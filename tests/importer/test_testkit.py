"""Tests for photree.importer.testkit module."""

from pathlib import Path

from photree.importer.testkit import seed_demo


class TestSeedDemo:
    def test_creates_image_capture_dir(self, tmp_path: Path) -> None:
        result = seed_demo(tmp_path)

        assert result.image_capture_dir.is_dir()
        files = sorted(f.name for f in result.image_capture_dir.iterdir())
        # All expected IC files present
        assert "IMG_0001.HEIC" in files
        assert "IMG_0001.AAE" in files
        assert "IMG_E0001.HEIC" in files
        assert "IMG_O0001.AAE" in files
        assert "IMG_0002.HEIC" in files
        assert "IMG_0003.DNG" in files
        assert "IMG_E0003.JPG" in files
        assert "IMG_0004.JPG" in files
        assert "IMG_0005.PNG" in files
        assert "IMG_0006.MOV" in files
        assert "IMG_0007.MOV" in files
        assert "IMG_E0007.MOV" in files

    def test_creates_album_with_selection(self, tmp_path: Path) -> None:
        result = seed_demo(tmp_path)

        assert result.album_dir.is_dir()
        assert result.selection_dir.is_dir()
        sel_files = sorted(f.name for f in result.selection_dir.iterdir())
        assert sel_files == [
            "IMG_0001.JPG",
            "IMG_0002.JPG",
            "IMG_0003.JPG",
            "IMG_0005.JPG",
            "IMG_0006.MOV",
            "IMG_0007.MOV",
        ]

    def test_heic_files_are_valid_when_sips_available(self, tmp_path: Path) -> None:
        import shutil

        result = seed_demo(tmp_path)

        heic = result.image_capture_dir / "IMG_0001.HEIC"
        if shutil.which("sips") is not None:
            # On macOS: sips converts to real HEIC (larger than the 347-byte JPEG source)
            assert heic.stat().st_size > 1000
        else:
            # On Linux: no sips, HEIC files keep JPEG content
            assert heic.stat().st_size > 0

    def test_custom_album_name(self, tmp_path: Path) -> None:
        result = seed_demo(tmp_path, album_name="2025-01-01 - New Year")

        assert result.album_dir.name == "2025-01-01 - New Year"
        assert result.selection_dir.is_dir()

    def test_img_0004_not_in_selection(self, tmp_path: Path) -> None:
        """IMG_0004 is intentionally excluded from selection."""
        result = seed_demo(tmp_path)

        sel_files = {f.name for f in result.selection_dir.iterdir()}
        assert "IMG_0004.JPG" not in sel_files
        # But it exists in IC
        ic_files = {f.name for f in result.image_capture_dir.iterdir()}
        assert "IMG_0004.JPG" in ic_files
