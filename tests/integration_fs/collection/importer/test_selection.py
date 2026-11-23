import csv
from pathlib import Path

from photree.collection.importer.selection import (
    SELECTION_CSV,
    SelectionEntry,
    SelectionError,
    SelectionErrorKind,
    has_selection,
    read_selection,
)


def _write_csv_bytes(collection_dir: Path, content: bytes) -> Path:
    csv_path = collection_dir / SELECTION_CSV
    csv_path.write_bytes(content)
    return csv_path


class TestReadSelectionCsv:
    def test_rows_are_read_when_header_has_byte_order_mark(
        self,
        tmp_path: Path,
    ) -> None:
        _write_csv_bytes(tmp_path, "﻿entry,date\nIMG_0001.HEIC,\n".encode())

        sources = read_selection(tmp_path)

        assert sources.errors == ()
        assert sources.csv_entries == (SelectionEntry("IMG_0001.HEIC"),)

    def test_headerless_csv_is_an_error(self, tmp_path: Path) -> None:
        csv_path = _write_csv_bytes(tmp_path, b"IMG_0001.HEIC,\nIMG_0002.HEIC,\n")

        sources = read_selection(tmp_path)

        assert sources.errors == (
            SelectionError(
                SelectionErrorKind.MISSING_ENTRY_COLUMN,
                csv_path,
                1,
                value="IMG_0001.HEIC,",
            ),
        )
        assert sources.csv_entries == ()

    def test_non_utf8_csv_is_an_error(self, tmp_path: Path) -> None:
        csv_path = _write_csv_bytes(
            tmp_path,
            "entry,date\nÉté.HEIC,\n".encode("latin-1"),
        )

        sources = read_selection(tmp_path)

        assert sources.errors == (
            SelectionError(SelectionErrorKind.NOT_UTF8, csv_path, None),
        )

    def test_malformed_csv_is_an_error(self, tmp_path: Path) -> None:
        oversized = "x" * (csv.field_size_limit() + 1)
        _write_csv_bytes(tmp_path, f"entry,date\n{oversized},\n".encode())

        sources = read_selection(tmp_path)

        assert [e.kind for e in sources.errors] == [SelectionErrorKind.MALFORMED_CSV]

    def test_empty_csv_has_no_rows_and_no_error(self, tmp_path: Path) -> None:
        _write_csv_bytes(tmp_path, b"")

        sources = read_selection(tmp_path)

        assert sources.errors == ()
        assert sources.merged == ()


class TestHasSelection:
    def test_unreadable_csv_counts_as_a_selection(self, tmp_path: Path) -> None:
        # So a batch import reports the broken file instead of skipping it.
        _write_csv_bytes(tmp_path, "entry\nÉté.HEIC\n".encode("latin-1"))

        assert has_selection(tmp_path) is True

    def test_header_only_csv_is_no_selection(self, tmp_path: Path) -> None:
        _write_csv_bytes(tmp_path, b"entry,date\n")

        assert has_selection(tmp_path) is False
