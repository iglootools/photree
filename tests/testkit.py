"""Factories for the files, albums and galleries the tests set up."""

from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.linking import LinkMode


def write_file(path: Path, content: str = "data") -> None:
    """Write *content* to *path*, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_files(directory: Path, names: list[str]) -> Path:
    """
    Create *directory* holding a file per name, and return it.

    Each file holds ``data-<name>``, so files with different names differ.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text(f"data-{name}", encoding="utf-8")
    return directory


def file_names(directory: Path) -> set[str]:
    """Return the names of the files in *directory*, none when it does not exist."""
    if not directory.is_dir():
        return set()
    return {f.name for f in directory.iterdir() if f.is_file()}


def mark_album(album_dir: Path, album_id: str | None = None) -> str:
    """Write the album's ``album.yaml`` with *album_id*, or a new ID; return the ID."""
    aid = album_id if album_id is not None else generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return aid


def add_ios_media_source(album_dir: Path) -> None:
    """Give the album a minimal iOS media source: one original, empty browsable dirs."""
    write_file(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


def add_emptied_std_media_source(album_dir: Path) -> None:
    """
    Give the album a std media source whose browsable directory is empty.

    The archive keeps one video (``std-nelu/orig-vid/clip.mov``) while
    ``nelu-vid/`` holds nothing, so ``fix --rm-upstream`` refuses to delete
    the whole archive unless forced.
    """
    write_file(album_dir / "std-nelu" / "orig-vid" / "clip.mov")
    (album_dir / "nelu-vid").mkdir(parents=True)


def make_album(
    parent: Path,
    name: str,
    *,
    album_id: str | None = None,
) -> tuple[Path, str]:
    """
    Create album *name* under *parent*, with a minimal iOS media source.

    Returns the album's directory and its ID (*album_id*, or a new one).
    """
    album_dir = parent / name
    add_ios_media_source(album_dir)
    return album_dir, mark_album(album_dir, album_id)


def make_gallery(
    parent: Path,
    *,
    link_mode: LinkMode = LinkMode.HARDLINK,
    faces_enabled: bool = True,
) -> Path:
    """Create a ``gallery`` directory under *parent* with its ``gallery.yaml``."""
    gallery = parent / "gallery"
    gallery.mkdir()
    save_gallery_metadata(
        gallery,
        GalleryMetadata(link_mode=link_mode, faces_enabled=faces_enabled),
    )
    return gallery


def make_gallery_album(
    gallery: Path,
    name: str,
    *,
    album_id: str | None = None,
) -> tuple[Path, str]:
    """:func:`make_album` in the gallery's year directory, ``albums/<year>/``."""
    return make_album(gallery / "albums" / name[:4], name, album_id=album_id)
