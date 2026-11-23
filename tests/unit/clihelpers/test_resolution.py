from pathlib import Path

from photree.clihelpers.resolution import format_invalid_metadata
from photree.foundation.metadata_io import InvalidMetadataError


class TestFormatInvalidMetadata:
    def test_derived_file_says_it_can_be_rebuilt(self) -> None:
        exc = InvalidMetadataError(
            Path("/g/album/.photree/cache/exif/main.yaml"),
            "not valid YAML",
            derived=True,
        )

        message = format_invalid_metadata(exc, Path("/g"))

        assert "album/.photree/cache/exif/main.yaml" in message
        assert "--refresh-exif-cache" in message
        assert "does not regenerate" not in message

    def test_source_file_says_to_restore_it(self) -> None:
        exc = InvalidMetadataError(Path("/g/album/.photree/album.yaml"), "empty")

        message = format_invalid_metadata(exc, Path("/g"))

        assert "Restore the file from a backup" in message
