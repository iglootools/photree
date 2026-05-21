"""User-facing messages for the exporter."""

from __future__ import annotations


def export_summary(album_name: str, files_copied: int, album_type: str) -> str:
    return f"Done. Exported {album_name} ({album_type}): {files_copied} file(s)."


def batch_export_summary(exported: int, failed: int) -> str:
    return f"\nDone. {exported} album(s) exported, {failed} failed."
