"""Test data generation for demo and testing purposes.

Generates realistic Image Capture directories and album selection folders
following the conventions documented in docs/domain.md.
"""

from __future__ import annotations

import shutil
import zlib
from dataclasses import dataclass
from pathlib import Path

from ....common.sips import convert_to_heic
from ....common.sysdeps import SystemDependency, WhichFn, is_available

# ---------------------------------------------------------------------------
# Minimal valid image generators (no external dependencies)
# ---------------------------------------------------------------------------

# Minimal valid 1x1 JPEG, generated with Pillow (quality 75). An earlier
# hand-written byte list was truncated: libjpeg decoded it but printed
# "Corrupt JPEG data: premature end of data segment" to stderr on every read.
_JPEG_BYTES = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000806060706050807070709"
    "09080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c283729"
    "2c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c21"
    "323232323232323232323232323232323232323232323232323232323232323232323232"
    "3232323232323232323232323232ffc00011080001000103012200021101031101ffc400"
    "1f0000010501010101010100000000000000000102030405060708090a0bffc400b51000"
    "02010303020403050504040000017d010203000411051221314106135161072271143281"
    "91a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a"
    "434445464748494a535455565758595a636465666768696a737475767778797a83848586"
    "8788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6"
    "c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc400"
    "1f0100030101010101010101010000000000000102030405060708090a0bffc400b51100"
    "020102040403040705040400010277000102031104052131061241510761711322328108"
    "144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a3536373839"
    "3a434445464748494a535455565758595a636465666768696a737475767778797a828384"
    "85868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4"
    "c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda00"
    "0c03010002110311003f0028a28a00ffd9"
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


# Image Capture files, grouped by image number, following the conventions
# documented in docs/domain.md. ``.HEIC`` entries start as JPEG content and are
# converted to real HEIC when sips is available.
_IMAGE_CAPTURE_FILES: tuple[tuple[str, bytes], ...] = (
    # 0001: HEIC with edits
    ("IMG_0001.HEIC", _JPEG_BYTES),
    ("IMG_0001.AAE", _AAE_BYTES),
    ("IMG_E0001.HEIC", _JPEG_BYTES),
    ("IMG_O0001.AAE", _AAE_BYTES),
    # 0002: HEIC without edits
    ("IMG_0002.HEIC", _JPEG_BYTES),
    ("IMG_0002.AAE", _AAE_BYTES),
    # 0003: ProRAW (DNG) with edited JPG — placeholder (valid DNG not feasible)
    ("IMG_0003.DNG", _JPEG_BYTES),
    ("IMG_0003.AAE", _AAE_BYTES),
    ("IMG_E0003.JPG", _JPEG_BYTES),
    ("IMG_O0003.AAE", _AAE_BYTES),
    # 0004: JPEG original (Most Compatible)
    ("IMG_0004.JPG", _JPEG_BYTES),
    ("IMG_0004.AAE", _AAE_BYTES),
    # 0005: PNG screenshot (no AAE)
    ("IMG_0005.PNG", _PNG_BYTES),
    # 0006: Video without edits
    ("IMG_0006.MOV", _MOV_PLACEHOLDER),
    # 0007: Video with edits
    ("IMG_0007.MOV", _MOV_PLACEHOLDER),
    ("IMG_E0007.MOV", _MOV_PLACEHOLDER),
    ("IMG_O0007.AAE", _AAE_BYTES),
    # 0008: Live Photo (HEIC + companion MOV, no edits)
    ("IMG_0008.HEIC", _JPEG_BYTES),
    ("IMG_0008.AAE", _AAE_BYTES),
    ("IMG_0008.MOV", _MOV_PLACEHOLDER),
    # 0009: Live Photo with edits (both image and video edited)
    ("IMG_0009.HEIC", _JPEG_BYTES),
    ("IMG_0009.AAE", _AAE_BYTES),
    ("IMG_0009.MOV", _MOV_PLACEHOLDER),
    ("IMG_E0009.HEIC", _JPEG_BYTES),
    ("IMG_O0009.AAE", _AAE_BYTES),
    ("IMG_E0009.MOV", _MOV_PLACEHOLDER),
)


def _convert_placeholders_to_heic(ic_dir: Path) -> None:
    """Replace the JPEG content of each ``.HEIC`` placeholder with real HEIC."""
    heic_paths = [
        ic_dir / name for name, _ in _IMAGE_CAPTURE_FILES if name.endswith(".HEIC")
    ]
    for heic_path in heic_paths:
        jpg_tmp = heic_path.with_suffix(".tmp.jpg")
        heic_path.rename(jpg_tmp)
        convert_to_heic(jpg_tmp, heic_path)
        jpg_tmp.unlink()


def _seed_image_capture(ic_dir: Path, *, which: WhichFn) -> None:
    """Generate a realistic Image Capture directory from ``_IMAGE_CAPTURE_FILES``.

    Covers HEIC photos with and without edits, ProRAW (DNG) with JPG edit,
    JPEG original (Most Compatible mode), PNG screenshot, MOV videos with and
    without edits, and Live Photos.
    """
    for name, data in _IMAGE_CAPTURE_FILES:
        _write(ic_dir / name, data)

    # Convert JPEG placeholders to valid HEIC files when sips is available
    # (macOS only). On Linux, HEIC files keep JPEG content — the import
    # workflow still works, but HEIC→JPEG conversion must use a noop converter.
    if is_available(SystemDependency.SIPS, which=which):
        _convert_placeholders_to_heic(ic_dir)


def _seed_album(album_dir: Path) -> None:
    """Generate an album with selection files in to-import-ios-main/.

    The selection files are JPEG exports from Apple Photos, matching a subset
    of the Image Capture files. IMG_0004 is intentionally excluded to
    demonstrate unselected photos.
    """
    selection_dir = album_dir / "to-import-ios-main"
    selection_dir.mkdir(parents=True, exist_ok=True)

    # JPEG selections (matching IC originals by number)
    for name in (
        "IMG_0001.JPG",
        "IMG_0002.JPG",
        "IMG_0003.JPG",
        "IMG_0005.JPG",
        "IMG_0008.JPG",
        "IMG_0009.JPG",
    ):
        _write(selection_dir / name, _JPEG_BYTES)

    # Video selections (same format as IC)
    for name in ("IMG_0006.MOV", "IMG_0007.MOV"):
        _write(selection_dir / name, _MOV_PLACEHOLDER)


def seed_demo(
    base_dir: Path,
    *,
    album_name: str = "2024-06-15 - Demo Album",
    which: WhichFn = shutil.which,
) -> SeedResult:
    """Generate a complete demo environment with Image Capture files and an album.

    Creates:
    - ``base_dir/image-capture/`` — realistic Image Capture directory
    - ``base_dir/<album_name>/to-import-ios-main/`` — album with selection files

    *which* probes PATH for ``sips``; HEIC placeholders keep JPEG content when
    it is absent.
    """
    base_dir.mkdir(parents=True, exist_ok=True)

    ic_dir = base_dir / "image-capture"
    ic_dir.mkdir(parents=True, exist_ok=True)
    _seed_image_capture(ic_dir, which=which)

    album_dir = base_dir / album_name
    _seed_album(album_dir)

    return SeedResult(
        base_dir=base_dir,
        image_capture_dir=ic_dir,
        album_dir=album_dir,
        selection_dir=album_dir / "to-import-ios-main",
    )
