"""Tests for photree.albums.output.exporter."""

from pathlib import Path

from photree.albums.cmd_handler.exporter import ExportFailure
from photree.albums.output.exporter import format_export_failure_reason


class TestFormatExportFailureReason:
    def test_collision_names_the_other_albums_and_the_target(
        self,
        tmp_path: Path,
    ) -> None:
        failure = ExportFailure(
            tmp_path / "2023" / "Misc",
            target_dir=tmp_path / "share" / "Misc",
            colliding_albums=(tmp_path / "2024" / "Misc",),
        )

        assert format_export_failure_reason(failure, tmp_path) == (
            'not exported: "2024/Misc" would export to the same directory,'
            " share/Misc; rename one of them"
        )

    def test_error_keeps_its_message(self, tmp_path: Path) -> None:
        failure = ExportFailure(tmp_path / "A", "No space left on device")

        assert (
            format_export_failure_reason(failure, tmp_path) == "No space left on device"
        )
