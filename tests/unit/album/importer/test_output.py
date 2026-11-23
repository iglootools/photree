"""Tests for photree.album.importer.output."""

from dataclasses import replace
from io import StringIO
from pathlib import Path

from rich.console import Console

from photree.album.importer.album_import import TaskIssue
from photree.album.importer.output import (
    format_preflight_troubleshoot,
    format_task_issue,
)
from photree.album.importer.std import StdUnsupportedEntries
from photree.album.importer.testkit.preflight import (
    IC_CHECK_WARNINGS,
    PREFLIGHT_FAILURES,
    PREFLIGHT_OK,
)
from photree.album.store.media_source import std_media_source

_CWD = Path("/albums")


def _render(markup: str) -> str:
    """Print *markup* as the CLI does, and return what the user sees."""
    out = StringIO()
    Console(file=out, width=500, highlight=False, color_system=None).print(markup)
    return out.getvalue()


class TestFormatTaskIssue:
    def test_unsupported_entries_named_with_the_way_out(self) -> None:
        issue = TaskIssue(
            std_media_source("nelu"),
            StdUnsupportedEntries(("orig/sub/", "orig/x.CR2")),
        )
        message = format_task_issue(issue)
        assert "2 entry(ies) would not be imported: orig/sub/, orig/x.CR2" in message
        assert "move the others out of it first" in message

    def test_unsupported_entries_truncated_after_ten(self) -> None:
        entries = tuple(f"orig/{i:02}.txt" for i in range(12))
        issue = TaskIssue(std_media_source("nelu"), StdUnsupportedEntries(entries))
        message = format_task_issue(issue)
        assert "orig/09.txt and 2 more." in message
        assert "orig/10.txt" not in message


class TestFormatPreflightTroubleshoot:
    def test_none_when_every_check_passes(self) -> None:
        assert format_preflight_troubleshoot(PREFLIGHT_OK, cwd=_CWD) is None

    def test_failed_image_capture_check_points_to_force(self) -> None:
        troubleshoot = format_preflight_troubleshoot(PREFLIGHT_FAILURES, cwd=_CWD)
        rendered = _render(troubleshoot or "")
        assert "does not look like an Image Capture folder" in rendered
        assert "Only 2/10 files" in rendered
        assert "--force" in rendered

    def test_image_capture_check_ignored_without_an_ios_task(self) -> None:
        result = replace(PREFLIGHT_OK, image_capture_dir_check=IC_CHECK_WARNINGS)
        std_only = replace(result, ios_import_required=False)
        assert format_preflight_troubleshoot(std_only, cwd=_CWD) is None
        assert "--force" in (format_preflight_troubleshoot(result, cwd=_CWD) or "")
