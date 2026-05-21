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

    def test_with_location(self) -> None:
        parsed = parse_collection_name("2024-07 - Summer Trip @ Banff NP, AB, CA")
        assert parsed == ParsedCollectionName(
            date="2024-07", title="Summer Trip", location="Banff NP, AB, CA"
        )

    def test_dateless_with_location(self) -> None:
        parsed = parse_collection_name("Road Trips @ Western Canada")
        assert parsed == ParsedCollectionName(
            date=None, title="Road Trips", location="Western Canada"
        )

    def test_with_private_tag(self) -> None:
        parsed = parse_collection_name("2024-07 - Summer Trip [private]")
        assert parsed == ParsedCollectionName(
            date="2024-07", title="Summer Trip", private=True
        )

    def test_dateless_with_private_tag(self) -> None:
        parsed = parse_collection_name("Secret Stuff [private]")
        assert parsed == ParsedCollectionName(
            date=None, title="Secret Stuff", private=True
        )

    def test_location_and_private(self) -> None:
        parsed = parse_collection_name(
            "2024-07 - Summer Trip @ Banff NP, AB, CA [private]"
        )
        assert parsed == ParsedCollectionName(
            date="2024-07",
            title="Summer Trip",
            location="Banff NP, AB, CA",
            private=True,
        )


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

    def test_with_location(self) -> None:
        parsed = ParsedCollectionName(date="2024-07", title="Trip", location="Banff")
        assert reconstruct_collection_name(parsed) == "2024-07 - Trip @ Banff"

    def test_with_private(self) -> None:
        parsed = ParsedCollectionName(date="2024-07", title="Trip", private=True)
        assert reconstruct_collection_name(parsed) == "2024-07 - Trip [private]"

    def test_location_and_private(self) -> None:
        parsed = ParsedCollectionName(
            date="2024-07", title="Trip", location="Banff", private=True
        )
        assert reconstruct_collection_name(parsed) == "2024-07 - Trip @ Banff [private]"

    def test_roundtrip_with_date(self) -> None:
        name = "2024-07-14 - Hiking the Rockies"
        assert reconstruct_collection_name(parse_collection_name(name)) == name

    def test_roundtrip_dateless(self) -> None:
        name = "Best of All Time"
        assert reconstruct_collection_name(parse_collection_name(name)) == name

    def test_roundtrip_with_location(self) -> None:
        name = "2024-07 - Summer Trip @ Banff NP, AB, CA"
        assert reconstruct_collection_name(parse_collection_name(name)) == name

    def test_roundtrip_with_private(self) -> None:
        name = "2024-07 - Summer Trip [private]"
        assert reconstruct_collection_name(parse_collection_name(name)) == name

    def test_roundtrip_location_and_private(self) -> None:
        name = "2024-07 - Summer Trip @ Banff NP, AB, CA [private]"
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

    def test_with_location_still_parses_year(self) -> None:
        assert parse_collection_year("2024-07 - Trip @ Banff") == "2024"

    def test_with_private_still_parses_year(self) -> None:
        assert parse_collection_year("2024-07 - Trip [private]") == "2024"
