"""Locate, load and save an album's EXIF cache files."""

from pathlib import Path

from photree.album.exif_cache.protocol import EXIF_CACHE_DIR, ExifCache
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    InvalidMetadataError,
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)


def exif_cache_dir(album_dir: Path) -> Path:
    """Return the directory holding *album_dir*'s EXIF cache files."""
    return album_dir / PHOTREE_DIR / EXIF_CACHE_DIR


def cache_path(album_dir: Path, media_source_name: str) -> Path:
    """Return the path of one media source's EXIF cache file."""
    return exif_cache_dir(album_dir) / f"{media_source_name}.yaml"


def load_exif_cache(album_dir: Path, media_source_name: str) -> ExifCache | None:
    """
    Load the EXIF cache, or return ``None`` when the file is absent.

    A present-but-corrupt file raises
    :class:`~photree.foundation.metadata_io.InvalidMetadataError`, marked
    ``derived``: the fix is ``album refresh --refresh-exif-cache`` or
    deleting the file — not silently reading around it.
    """
    path = cache_path(album_dir, media_source_name)
    try:
        raw = load_yaml_mapping(path)
        return validate_metadata(path, ExifCache, raw) if raw is not None else None
    except InvalidMetadataError as exc:
        raise InvalidMetadataError(exc.path, exc.reason, derived=True) from exc


def save_exif_cache(album_dir: Path, media_source_name: str, cache: ExifCache) -> None:
    """Write *cache* as one media source's cache file, creating its directory."""
    path = cache_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, cache.model_dump(by_alias=True, mode="json"))
