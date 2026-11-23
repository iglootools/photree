from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.id import generate_collection_id
from photree.collection.importer.import_members import (
    CollectionImportError,
    CollectionImportErrorKind,
)
from photree.collection.importer.resolve import GalleryIndex, scan_gallery
from photree.collection.importer.selection import SELECTION_CSV
from photree.collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
)
from photree.collections.cmd_handler.import_members import batch_import
from tests.testkit import make_gallery


def _setup_album(gallery: Path, name: str) -> str:
    album_dir = gallery / "albums" / "2024" / name
    (album_dir / "ios-main" / "orig-img").mkdir(parents=True)
    album_id = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=album_id))
    return album_id


def _setup_collection(gallery: Path, name: str, entries: list[str] | None) -> Path:
    col_dir = gallery / "collections" / "2024" / name
    col_dir.mkdir(parents=True)
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        ),
    )
    if entries is not None:
        (col_dir / SELECTION_CSV).write_text(
            "\n".join(["entry,date", *(f"{e}," for e in entries)]) + "\n",
            encoding="utf-8",
        )
    return col_dir


class TestBatchImport:
    def test_imports_skips_and_fails_independently(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        album_id = _setup_album(gallery, "2024-07-14 - Trip")
        good = _setup_collection(gallery, "2024-07 - Good", ["2024-07-14 - Trip"])
        empty = _setup_collection(gallery, "2024-08 - Empty", None)
        bad = _setup_collection(gallery, "2024-09 - Bad", ["nonexistent"])
        events: list[tuple[str, str, tuple[str, ...]]] = []

        def on_end(
            name: str,
            /,
            *,
            success: bool,
            error_labels: tuple[str, ...],
        ) -> None:
            events.append((f"end success={success}", name, error_labels))

        result = batch_import(
            [good, empty, bad],
            gallery,
            on_skipped=lambda name: events.append(("skipped", name, ())),
            on_start=lambda name: events.append(("start", name, ())),
            on_end=on_end,
        )

        assert result.skipped == (empty,)
        assert [(o.collection_dir, o.success) for o in result.outcomes] == [
            (good, True),
            (bad, False),
        ]
        assert events == [
            ("skipped", empty.name, ()),
            ("start", good.name, ()),
            ("end success=True", good.name, ()),
            ("start", bad.name, ()),
            ("end success=False", bad.name, ("1 error(s)",)),
        ]
        loaded = load_collection_metadata(good)
        assert loaded is not None
        assert loaded.albums == [album_id]

    def test_collection_level_error_is_captured(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        col_dir = gallery / "collections" / "2024" / "2024-07 - Uninitialized"
        col_dir.mkdir(parents=True)
        (col_dir / SELECTION_CSV).write_text("entry\nx\n", encoding="utf-8")

        result = batch_import([col_dir], gallery)

        [outcome] = result.outcomes
        assert outcome.result is None
        assert isinstance(outcome.error, CollectionImportError)
        assert outcome.error.kind == CollectionImportErrorKind.NO_METADATA

    def test_gallery_is_scanned_once_per_batch(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Trip")
        first = _setup_collection(gallery, "2024-07 - One", ["2024-07-14 - Trip"])
        second = _setup_collection(gallery, "2024-08 - Two", ["2024-07-14 - Trip"])
        scanned: list[Path] = []

        def counting_scan(gallery_dir: Path) -> GalleryIndex:
            scanned.append(gallery_dir)
            return scan_gallery(gallery_dir)

        result = batch_import([first, second], gallery, scan=counting_scan)

        assert [o.success for o in result.outcomes] == [True, True]
        assert scanned == [gallery]
