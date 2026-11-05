from pathlib import Path

from ...foundation.layout import PHOTREE_DIR
from ...foundation.metadata_io import load_yaml_mapping, validate_metadata, write_yaml
from .protocol import EXIF_CACHE_DIR, ExifCache


def exif_cache_dir(album_dir: Path) -> Path:
    return album_dir / PHOTREE_DIR / EXIF_CACHE_DIR


def cache_path(album_dir: Path, media_source_name: str) -> Path:
    return exif_cache_dir(album_dir) / f"{media_source_name}.yaml"


def load_exif_cache(album_dir: Path, media_source_name: str) -> ExifCache | None:
    """Returns ``None`` when the file is absent. A present-but-corrupt file
    raises :class:`~photree.foundation.metadata_io.InvalidMetadataError`; the cache is
    derived data, so the fix is ``album refresh --refresh-exif-cache`` or
    deleting the file — not silently reading around it.
    """
    path = cache_path(album_dir, media_source_name)
    raw = load_yaml_mapping(path)
    return validate_metadata(path, ExifCache, raw) if raw is not None else None


def save_exif_cache(album_dir: Path, media_source_name: str, cache: ExifCache) -> None:
    path = cache_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, cache.model_dump(by_alias=True, mode="json"))
