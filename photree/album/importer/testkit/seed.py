"""Test data generation for demo and testing purposes.

Generates realistic Image Capture directories and album selection folders
following the conventions documented in docs/internals.md.
"""

from __future__ import annotations

import shutil
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal valid image generators (no external dependencies)
# ---------------------------------------------------------------------------

# Minimal valid 1x1 JPEG (347 bytes)
_JPEG_BYTES = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xE0,
        0x00,
        0x10,
        0x4A,
        0x46,
        0x49,
        0x46,
        0x00,
        0x01,
        0x01,
        0x00,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        0x00,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x00,
        0x08,
        0x06,
        0x06,
        0x07,
        0x06,
        0x05,
        0x08,
        0x07,
        0x07,
        0x07,
        0x09,
        0x09,
        0x08,
        0x0A,
        0x0C,
        0x14,
        0x0D,
        0x0C,
        0x0B,
        0x0B,
        0x0C,
        0x19,
        0x12,
        0x13,
        0x0F,
        0x14,
        0x1D,
        0x1A,
        0x1F,
        0x1E,
        0x1D,
        0x1A,
        0x1C,
        0x1C,
        0x20,
        0x24,
        0x2E,
        0x27,
        0x20,
        0x22,
        0x2C,
        0x23,
        0x1C,
        0x1C,
        0x28,
        0x37,
        0x29,
        0x2C,
        0x30,
        0x31,
        0x34,
        0x34,
        0x34,
        0x1F,
        0x27,
        0x39,
        0x3D,
        0x38,
        0x32,
        0x3C,
        0x2E,
        0x33,
        0x34,
        0x32,
        0xFF,
        0xC0,
        0x00,
        0x0B,
        0x08,
        0x00,
        0x01,
        0x00,
        0x01,
        0x01,
        0x01,
        0x11,
        0x00,
        0xFF,
        0xC4,
        0x00,
        0x1F,
        0x00,
        0x00,
        0x01,
        0x05,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0x09,
        0x0A,
        0x0B,
        0xFF,
        0xC4,
        0x00,
        0xB5,
        0x10,
        0x00,
        0x02,
        0x01,
        0x03,
        0x03,
        0x02,
        0x04,
        0x03,
        0x05,
        0x05,
        0x04,
        0x04,
        0x00,
        0x00,
        0x01,
        0x7D,
        0x01,
        0x02,
        0x03,
        0x00,
        0x04,
        0x11,
        0x05,
        0x12,
        0x21,
        0x31,
        0x41,
        0x06,
        0x13,
        0x51,
        0x61,
        0x07,
        0x22,
        0x71,
        0x14,
        0x32,
        0x81,
        0x91,
        0xA1,
        0x08,
        0x23,
        0x42,
        0xB1,
        0xC1,
        0x15,
        0x52,
        0xD1,
        0xF0,
        0x24,
        0x33,
        0x62,
        0x72,
        0x82,
        0x09,
        0x0A,
        0x16,
        0x17,
        0x18,
        0x19,
        0x1A,
        0x25,
        0x26,
        0x27,
        0x28,
        0x29,
        0x2A,
        0x34,
        0x35,
        0x36,
        0x37,
        0x38,
        0x39,
        0x3A,
        0x43,
        0x44,
        0x45,
        0x46,
        0x47,
        0x48,
        0x49,
        0x4A,
        0x53,
        0x54,
        0x55,
        0x56,
        0x57,
        0x58,
        0x59,
        0x5A,
        0x63,
        0x64,
        0x65,
        0x66,
        0x67,
        0x68,
        0x69,
        0x6A,
        0x73,
        0x74,
        0x75,
        0x76,
        0x77,
        0x78,
        0x79,
        0x7A,
        0x83,
        0x84,
        0x85,
        0x86,
        0x87,
        0x88,
        0x89,
        0x8A,
        0x92,
        0x93,
        0x94,
        0x95,
        0x96,
        0x97,
        0x98,
        0x99,
        0x9A,
        0xA2,
        0xA3,
        0xA4,
        0xA5,
        0xA6,
        0xA7,
        0xA8,
        0xA9,
        0xAA,
        0xB2,
        0xB3,
        0xB4,
        0xB5,
        0xB6,
        0xB7,
        0xB8,
        0xB9,
        0xBA,
        0xC2,
        0xC3,
        0xC4,
        0xC5,
        0xC6,
        0xC7,
        0xC8,
        0xC9,
        0xCA,
        0xD2,
        0xD3,
        0xD4,
        0xD5,
        0xD6,
        0xD7,
        0xD8,
        0xD9,
        0xDA,
        0xE1,
        0xE2,
        0xE3,
        0xE4,
        0xE5,
        0xE6,
        0xE7,
        0xE8,
        0xE9,
        0xEA,
        0xF1,
        0xF2,
        0xF3,
        0xF4,
        0xF5,
        0xF6,
        0xF7,
        0xF8,
        0xF9,
        0xFA,
        0xFF,
        0xDA,
        0x00,
        0x08,
        0x01,
        0x01,
        0x00,
        0x00,
        0x3F,
        0x00,
        0x7B,
        0x94,
        0x11,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0xFF,
        0xD9,
    ]
)


def _make_png() -> bytes:
    """Generate a minimal valid 1x1 white PNG."""
    # IHDR: 1x1, 8-bit RGB
    ihdr_data = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data).to_bytes(4, "big")
    ihdr = b"\x00\x00\x00\x0d" + b"IHDR" + ihdr_data + ihdr_crc

    # IDAT: single white pixel (filter byte 0x00 + RGB 0xFF 0xFF 0xFF)
    raw = zlib.compress(b"\x00\xff\xff\xff")
    idat_crc = zlib.crc32(b"IDAT" + raw).to_bytes(4, "big")
    idat = len(raw).to_bytes(4, "big") + b"IDAT" + raw + idat_crc

    # IEND
    iend_crc = zlib.crc32(b"IEND").to_bytes(4, "big")
    iend = b"\x00\x00\x00\x00" + b"IEND" + iend_crc

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


_PNG_BYTES = _make_png()

_AAE_BYTES = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>adjustmentFormatVersion</key>
    <integer>1</integer>
</dict>
</plist>
"""

_MOV_PLACEHOLDER = b"placeholder-mov"


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _convert_jpeg_to_heic(src: Path, dst: Path) -> None:
    """Convert a JPEG file to HEIC using macOS sips."""
    subprocess.run(
        ["sips", "-s", "format", "heic", str(src), "--out", str(dst)],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Image Capture directory generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedResult:
    """Result of seeding a demo environment."""

    base_dir: Path
    image_capture_dir: Path
    album_dir: Path
    selection_dir: Path


def _seed_image_capture(ic_dir: Path) -> None:
    """Generate a realistic Image Capture directory.

    Creates files matching the conventions documented in docs/internals.md:
    - HEIC photos with and without edits
    - ProRAW (DNG) with JPG edit
    - JPEG original (Most Compatible mode)
    - PNG screenshot
    - MOV videos with and without edits
    """
    # 0001: HEIC with edits
    _write(ic_dir / "IMG_0001.HEIC", _JPEG_BYTES)  # temporary JPEG, converted below
    _write(ic_dir / "IMG_0001.AAE", _AAE_BYTES)
    _write(ic_dir / "IMG_E0001.HEIC", _JPEG_BYTES)  # temporary JPEG, converted below
    _write(ic_dir / "IMG_O0001.AAE", _AAE_BYTES)

    # 0002: HEIC without edits
    _write(ic_dir / "IMG_0002.HEIC", _JPEG_BYTES)  # temporary JPEG, converted below
    _write(ic_dir / "IMG_0002.AAE", _AAE_BYTES)

    # 0003: ProRAW (DNG) with edited JPG
    _write(ic_dir / "IMG_0003.DNG", _JPEG_BYTES)  # placeholder (valid DNG not feasible)
    _write(ic_dir / "IMG_0003.AAE", _AAE_BYTES)
    _write(ic_dir / "IMG_E0003.JPG", _JPEG_BYTES)
    _write(ic_dir / "IMG_O0003.AAE", _AAE_BYTES)

    # 0004: JPEG original (Most Compatible)
    _write(ic_dir / "IMG_0004.JPG", _JPEG_BYTES)
    _write(ic_dir / "IMG_0004.AAE", _AAE_BYTES)

    # 0005: PNG screenshot (no AAE)
    _write(ic_dir / "IMG_0005.PNG", _PNG_BYTES)

    # 0006: Video without edits
    _write(ic_dir / "IMG_0006.MOV", _MOV_PLACEHOLDER)

    # 0007: Video with edits
    _write(ic_dir / "IMG_0007.MOV", _MOV_PLACEHOLDER)
    _write(ic_dir / "IMG_E0007.MOV", _MOV_PLACEHOLDER)
    _write(ic_dir / "IMG_O0007.AAE", _AAE_BYTES)

    # Convert JPEG placeholders to valid HEIC files when sips is available
    # (macOS only). On Linux, HEIC files keep JPEG content — the import
    # workflow still works, but HEIC→JPEG conversion must use a noop converter.
    if shutil.which("sips") is not None:
        for name in ("IMG_0001.HEIC", "IMG_E0001.HEIC", "IMG_0002.HEIC"):
            heic_path = ic_dir / name
            jpg_tmp = heic_path.with_suffix(".tmp.jpg")
            heic_path.rename(jpg_tmp)
            _convert_jpeg_to_heic(jpg_tmp, heic_path)
            jpg_tmp.unlink()


def _seed_album(album_dir: Path) -> None:
    """Generate an album with selection files in to-import/.

    The selection files are JPEG exports from Apple Photos, matching a subset
    of the Image Capture files. IMG_0004 is intentionally excluded to
    demonstrate unselected photos.
    """
    selection_dir = album_dir / "to-import"
    selection_dir.mkdir(parents=True, exist_ok=True)

    # JPEG selections (matching IC originals by number)
    for name in ("IMG_0001.JPG", "IMG_0002.JPG", "IMG_0003.JPG", "IMG_0005.JPG"):
        _write(selection_dir / name, _JPEG_BYTES)

    # Video selections (same format as IC)
    for name in ("IMG_0006.MOV", "IMG_0007.MOV"):
        _write(selection_dir / name, _MOV_PLACEHOLDER)


def seed_demo(
    base_dir: Path,
    *,
    album_name: str = "2024-06-15 - Demo Album",
) -> SeedResult:
    """Generate a complete demo environment with Image Capture files and an album.

    Creates:
    - ``base_dir/image-capture/`` — realistic Image Capture directory
    - ``base_dir/<album_name>/to-import/`` — album with selection files
    """
    base_dir.mkdir(parents=True, exist_ok=True)

    ic_dir = base_dir / "image-capture"
    ic_dir.mkdir(parents=True, exist_ok=True)
    _seed_image_capture(ic_dir)

    album_dir = base_dir / album_name
    _seed_album(album_dir)

    return SeedResult(
        base_dir=base_dir,
        image_capture_dir=ic_dir,
        album_dir=album_dir,
        selection_dir=album_dir / "to-import",
    )
