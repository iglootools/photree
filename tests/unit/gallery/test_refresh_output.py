from pathlib import Path

from photree.collection.refresh.result import CollectionRefreshResult
from photree.gallery.browsable_refresh import (
    BrowsableRefreshError,
    BrowsableRefreshErrorKind,
)
from photree.gallery.cli.refresh_output import (
    format_browsable_error,
    format_collection_changes,
)

CWD = Path("/gallery")


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


class TestFormatBrowsableError:
    def test_link_collision_names_the_link_and_every_target(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.LINK_COLLISION,
            CWD / "browsable" / "public" / "Trip" / "main-jpg",
            targets=(
                CWD / "albums" / "a" / "Trip" / "main-jpg",
                CWD / "albums" / "b" / "Trip" / "main-jpg",
            ),
        )

        assert format_browsable_error(error, CWD) == (
            "browsable link browsable/public/Trip/main-jpg would point to more "
            "than one target:\n"
            "  albums/a/Trip/main-jpg\n"
            "  albums/b/Trip/main-jpg\n"
            "Two albums or collections share a name there: rename one of them, "
            "then run 'photree gallery refresh'."
        )
