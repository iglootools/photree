from datetime import datetime

from photree.collection.importer.output import format_resolution_error
from photree.collection.importer.resolve import ResolutionError, ResolutionErrorKind


class TestFormatResolutionError:
    def test_entry_without_date_hint_shows_the_entry_alone(self) -> None:
        error = ResolutionError("IMG_0001.HEIC", ResolutionErrorKind.NOT_FOUND)

        assert format_resolution_error(error) == (
            "[IMG_0001.HEIC] not found in gallery"
        )

    def test_date_hint_tells_apart_entries_with_the_same_value(self) -> None:
        error = ResolutionError(
            "IMG_0001.HEIC",
            ResolutionErrorKind.NOT_FOUND,
            date_hint=datetime(2024, 8, 10),
        )

        assert format_resolution_error(error) == (
            "[IMG_0001.HEIC] (date 2024-08-10T00:00:00) not found in gallery"
        )
