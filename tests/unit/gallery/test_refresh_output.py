from photree.collection.refresh.result import CollectionRefreshResult
from photree.gallery.cli.refresh_output import format_collection_changes


class TestFormatCollectionChanges:
    def test_deleted_collection_with_kept_directory_says_so(self) -> None:
        result = CollectionRefreshResult(
            deleted=("2024-07-14 - Gone", "2024-07-15 - Kept"),
            kept_directories=("2024-07-15 - Kept",),
        )

        assert format_collection_changes(result) == [
            "deleted: 2024-07-14 - Gone",
            "deleted: 2024-07-15 - Kept (directory kept: it holds other files)",
        ]
