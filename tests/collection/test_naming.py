"""Tests for collection naming convention parsing."""

from __future__ import annotations

from photree.collection.naming import (
    ParsedCollectionName,
    parse_collection_name,
    parse_collection_year,
    reconstruct_collection_name,
)


class TestParseCollectionName:
    def test_date_and_title(self) -> None:
        parsed = parse_collection_name("2024-07-14 - Hiking the Rockies")
        assert parsed == ParsedCollectionName(
            date="2024-07-14", title="Hiking the Rockies"
        )

    def test_date_range_and_title(self) -> None:
        parsed = parse_collection_name("2024-07--2024-08 - Summer Road Trip")
        assert parsed == ParsedCollectionName(
            date="2024-07--2024-08", title="Summer Road Trip"
        )

    def test_year_only_and_title(self) -> None:
        parsed = parse_collection_name("2024 - Family Photos")
        assert parsed == ParsedCollectionName(date="2024", title="Family Photos")

    def test_dateless_title(self) -> None:
        parsed = parse_collection_name("Best of All Time")
        assert parsed == ParsedCollectionName(date=None, title="Best of All Time")

    def test_month_precision(self) -> None:
        parsed = parse_collection_name("2024-07 - July Adventures")
        assert parsed == ParsedCollectionName(date="2024-07", title="July Adventures")

    def test_mixed_precision_range(self) -> None:
        parsed = parse_collection_name("2024-07--2024-08-03 - Trip")
        assert parsed == ParsedCollectionName(date="2024-07--2024-08-03", title="Trip")


class TestReconstructCollectionName:
    def test_with_date(self) -> None:
        parsed = ParsedCollectionName(date="2024-07-14", title="Hiking")
        assert reconstruct_collection_name(parsed) == "2024-07-14 - Hiking"

    def test_date_range(self) -> None:
        parsed = ParsedCollectionName(date="2024-07--2024-08", title="Summer")
        assert reconstruct_collection_name(parsed) == "2024-07--2024-08 - Summer"

    def test_dateless(self) -> None:
        parsed = ParsedCollectionName(date=None, title="Best of All Time")
        assert reconstruct_collection_name(parsed) == "Best of All Time"

    def test_roundtrip_with_date(self) -> None:
        name = "2024-07-14 - Hiking the Rockies"
        assert reconstruct_collection_name(parse_collection_name(name)) == name

    def test_roundtrip_dateless(self) -> None:
        name = "Best of All Time"
        assert reconstruct_collection_name(parse_collection_name(name)) == name


class TestParseCollectionYear:
    def test_day_date(self) -> None:
        assert parse_collection_year("2024-07-14 - Hiking") == "2024"

    def test_range_uses_start_year(self) -> None:
        assert parse_collection_year("2024-07--2025-01 - Trip") == "2024"

    def test_year_only(self) -> None:
        assert parse_collection_year("2024 - Photos") == "2024"

    def test_dateless_returns_none(self) -> None:
        assert parse_collection_year("Best of All Time") is None
