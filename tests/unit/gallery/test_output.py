from pathlib import Path

from photree.gallery.cmd_handler.importer import (
    AlbumImportFailure,
    BatchImportResult,
)
from photree.gallery.output import format_import_all_summary, import_all_failed


class TestImportAllOutcome:
    """How the import and post-import check outcomes drive import-all's exit."""

    def test_post_import_check_failure_fails_the_run(self, tmp_path: Path) -> None:
        """Regression: post-import check failures did not affect the exit code."""
        source = tmp_path / "incoming" / "2024-07-14 - Hiking"
        target = tmp_path / "gallery" / "albums" / "2024" / source.name
        result = BatchImportResult(imported=(source,))

        assert import_all_failed(result, [target])
        assert format_import_all_summary(result, [target], 0) == (
            "Done. 1 album(s) imported, 0 failed, 1 failed post-import check."
        )

    def test_import_failure_fails_the_run(self, tmp_path: Path) -> None:
        source = tmp_path / "incoming" / "2024-07-14 - Hiking"
        result = BatchImportResult(
            failures=(AlbumImportFailure(source, OSError("disk full")),),
        )

        assert import_all_failed(result, [])
        assert format_import_all_summary(result, [], 0) == (
            "Done. 0 album(s) imported, 1 failed."
        )

    def test_clean_run_succeeds_and_counts_skips(self, tmp_path: Path) -> None:
        result = BatchImportResult(imported=(tmp_path / "2024-07-14 - Hiking",))

        assert not import_all_failed(result, [])
        assert format_import_all_summary(result, [], 2) == (
            "Done. 1 album(s) imported, 0 failed, 2 skipped."
        )
