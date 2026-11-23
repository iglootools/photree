"""Tests for photree.album.importer.output."""

from photree.album.importer.album_import import TaskIssue
from photree.album.importer.output import format_task_issue
from photree.album.importer.std import StdUnsupportedEntries
from photree.album.store.media_source import std_media_source


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
