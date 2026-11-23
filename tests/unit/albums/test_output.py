from pathlib import Path

from photree.album.id import format_album_external_id, generate_album_id
from photree.albums.output import format_duplicate_ids_report

_CWD = Path("/gallery")


class TestFormatDuplicateIdsReport:
    def test_suggests_new_ids_only_for_the_copies(self) -> None:
        # Regression: the report suggested an unscoped 'fix --new-id', which
        # re-IDs every album it scans, orphaning collection and face references.
        shared_a = generate_album_id()
        shared_b = generate_album_id()
        report = format_duplicate_ids_report(
            {
                shared_a: (_CWD / "2024 - A", _CWD / "2024 - A copy"),
                shared_b: (_CWD / "2025 - B", _CWD / "B1", _CWD / "B2"),
            },
            _CWD,
        )

        assert format_album_external_id(shared_a) in report
        assert (
            '\'photree albums fix --new-id --album-dir "2024 - A copy" '
            '--album-dir "B1" --album-dir "B2"\''
        ) in report
