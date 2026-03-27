"""Tests for photree.album.naming module."""

from __future__ import annotations

from datetime import datetime

from photree.album.naming import (
    ParsedAlbumName,
    _album_date_range,
    _timestamp_matches_album_date,
    check_album_naming,
    check_batch_date_collisions,
    parse_album_name,
    reconstruct_name,
)


# ---------------------------------------------------------------------------
# parse_album_name
# ---------------------------------------------------------------------------


class TestParseAlbumName:
    def test_simple_date_and_title(self) -> None:
        result = parse_album_name("2024-06-15 - Beach Day")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series=None,
            title="Beach Day",
            location=None,
        )

    def test_date_range(self) -> None:
        result = parse_album_name("2024-06-15--2024-06-20 - Road Trip")
        assert result == ParsedAlbumName(
            date="2024-06-15--2024-06-20",
            part=None,
            private=False,
            series=None,
            title="Road Trip",
            location=None,
        )

    def test_with_part_number(self) -> None:
        result = parse_album_name("2024-06-15 - 01 - Morning Walk")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part="01",
            private=False,
            series=None,
            title="Morning Walk",
            location=None,
        )

    def test_with_series(self) -> None:
        result = parse_album_name("2024-06-15 - Canadian Rockies - Morning Walk")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series="Canadian Rockies",
            title="Morning Walk",
            location=None,
        )

    def test_with_part_and_series(self) -> None:
        result = parse_album_name("2024-06-15 - 01 - Canadian Rockies - Morning Walk")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part="01",
            private=False,
            series="Canadian Rockies",
            title="Morning Walk",
            location=None,
        )

    def test_with_private_tag(self) -> None:
        result = parse_album_name("2024-06-15 - Beach Day [private]")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=True,
            series=None,
            title="Beach Day",
            location=None,
        )

    def test_with_part_series_and_private(self) -> None:
        result = parse_album_name("2024-06-15 - 02 - Vacation - Dinner [private]")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part="02",
            private=True,
            series="Vacation",
            title="Dinner",
            location=None,
        )

    def test_parenthesized_content_in_title(self) -> None:
        result = parse_album_name("2024-06-15 - Hiking (Day 2)")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series=None,
            title="Hiking (Day 2)",
            location=None,
        )

    def test_parenthesized_content_with_series(self) -> None:
        result = parse_album_name("2024-06-15 - Alps - Hiking (Day 2)")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series="Alps",
            title="Hiking (Day 2)",
            location=None,
        )

    def test_series_with_part_after_series(self) -> None:
        result = parse_album_name("2024-06-15 - Trace des Caps - 01 - Anse Caritan")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part="01",
            private=False,
            series="Trace des Caps",
            title="Anse Caritan",
            location=None,
        )

    def test_returns_none_for_no_date(self) -> None:
        assert parse_album_name("random folder") is None

    def test_year_only(self) -> None:
        result = parse_album_name("2024 - Year Album")
        assert result is not None
        assert result.date == "2024"
        assert result.title == "Year Album"

    def test_year_month(self) -> None:
        result = parse_album_name("2024-06 - Summer")
        assert result is not None
        assert result.date == "2024-06"
        assert result.title == "Summer"

    def test_year_range(self) -> None:
        result = parse_album_name("2023--2024 - Two Years")
        assert result is not None
        assert result.date == "2023--2024"

    def test_mixed_precision_range(self) -> None:
        result = parse_album_name("2024-06--2024-08-15 - Summer Trip")
        assert result is not None
        assert result.date == "2024-06--2024-08-15"

    def test_month_range(self) -> None:
        result = parse_album_name("2024-06--2024-08 - Summer")
        assert result is not None
        assert result.date == "2024-06--2024-08"

    def test_returns_none_for_legacy_day_range(self) -> None:
        assert parse_album_name("2024-06-15-17 - Weekend Trip") is None

    def test_returns_none_for_legacy_enumerated_days(self) -> None:
        assert parse_album_name("2024-06-15,16 - Two Days") is None

    def test_extra_dashes_merged_to_spaces(self) -> None:
        result = parse_album_name("2024-06-15 - Trip - Lake Louise - Morning Walk")
        assert result is not None
        assert result.series == "Trip"
        assert result.title == "Lake Louise Morning Walk"

    def test_comma_in_title_preserved(self) -> None:
        result = parse_album_name("2024-06-15 - BBQ with friends, family")
        assert result is not None
        assert result.title == "BBQ with friends, family"
        assert result.location is None

    def test_location_extracted(self) -> None:
        result = parse_album_name("2024-06-15 - Beach Day @ Malibu")
        assert result == ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series=None,
            title="Beach Day",
            location="Malibu",
        )

    def test_location_with_commas(self) -> None:
        result = parse_album_name("2024-06-15 - Hike @ Banff NP, AB, CA")
        assert result is not None
        assert result.title == "Hike"
        assert result.location == "Banff NP, AB, CA"

    def test_location_with_series_and_private(self) -> None:
        result = parse_album_name(
            "2024-06-15 - 01 - Rockies - Hike @ Banff NP [private]"
        )
        assert result is not None
        assert result.part == "01"
        assert result.series == "Rockies"
        assert result.title == "Hike"
        assert result.location == "Banff NP"
        assert result.private is True

    def test_no_location_without_at(self) -> None:
        result = parse_album_name("2024-06-15 - Beach Day")
        assert result is not None
        assert result.location is None


# ---------------------------------------------------------------------------
# reconstruct_name
# ---------------------------------------------------------------------------


class TestReconstructName:
    def test_simple(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series=None,
            title="Beach Day",
            location=None,
        )
        assert reconstruct_name(parsed) == "2024-06-15 - Beach Day"

    def test_with_part(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part="1",
            private=False,
            series=None,
            title="Walk",
            location=None,
        )
        assert reconstruct_name(parsed) == "2024-06-15 - 01 - Walk"

    def test_with_series(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series="Rockies",
            title="Hike",
            location=None,
        )
        assert reconstruct_name(parsed) == "2024-06-15 - Rockies - Hike"

    def test_with_private(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=True,
            series=None,
            title="Dinner",
            location=None,
        )
        assert reconstruct_name(parsed) == "2024-06-15 - Dinner [private]"

    def test_full(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part="3",
            private=True,
            series="Vacation",
            title="Beach",
            location=None,
        )
        assert reconstruct_name(parsed) == (
            "2024-06-15 - 03 - Vacation - Beach [private]"
        )

    def test_date_range(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15--2024-06-20",
            part=None,
            private=False,
            series=None,
            title="Trip",
            location=None,
        )
        assert reconstruct_name(parsed) == "2024-06-15--2024-06-20 - Trip"

    def test_with_location(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part=None,
            private=False,
            series=None,
            title="Hike",
            location="Banff NP, AB, CA",
        )
        assert reconstruct_name(parsed) == "2024-06-15 - Hike @ Banff NP, AB, CA"

    def test_full_with_location(self) -> None:
        parsed = ParsedAlbumName(
            date="2024-06-15",
            part="1",
            private=True,
            series="Rockies",
            title="Hike",
            location="Banff NP",
        )
        assert reconstruct_name(parsed) == (
            "2024-06-15 - 01 - Rockies - Hike @ Banff NP [private]"
        )

    def test_roundtrip_canonical_names(self) -> None:
        canonical_names = [
            "2024-06-15 - Beach Day",
            "2024-06-15 - 01 - Morning Walk",
            "2024-06-15 - Canadian Rockies - Morning Walk",
            "2024-06-15 - 01 - Canadian Rockies - Morning Walk",
            "2024-06-15 - Beach Day [private]",
            "2024-06-15--2024-06-20 - Road Trip",
            "2024 - Year Album",
            "2024-06 - Summer",
            "2023--2024 - Two Years",
            "2024-06--2024-08-15 - Summer Trip",
            "2024-06-15 - Hiking (Day 2)",
            "2024-06-15 - Beach Day (bis)",
            "2024-06-15 - Hike @ Banff NP, AB, CA",
            "2024-06-15 - 01 - Rockies - Hike @ Banff NP [private]",
        ]
        for name in canonical_names:
            parsed = parse_album_name(name)
            assert parsed is not None, f"failed to parse: {name}"
            assert reconstruct_name(parsed) == name, f"roundtrip failed: {name}"


# ---------------------------------------------------------------------------
# check_album_naming
# ---------------------------------------------------------------------------


class TestCheckAlbumNaming:
    def test_valid_name_no_issues(self) -> None:
        assert check_album_naming("2024-06-15 - Beach Day") == ()

    def test_valid_with_private(self) -> None:
        assert check_album_naming("2024-06-15 - Beach Day [private]") == ()

    def test_valid_with_part_and_series(self) -> None:
        assert check_album_naming("2024-06-15 - 01 - Trip - Hike") == ()

    def test_valid_date_range(self) -> None:
        assert check_album_naming("2024-06-15--2024-06-20 - Road Trip") == ()

    def test_unparseable(self) -> None:
        issues = check_album_naming("random folder")
        assert len(issues) == 1
        assert issues[0].code == "unparseable"

    def test_valid_year_only(self) -> None:
        assert check_album_naming("2024 - Year Album") == ()

    def test_valid_month_only(self) -> None:
        assert check_album_naming("2024-06 - Summer") == ()

    def test_valid_mixed_range(self) -> None:
        assert check_album_naming("2024-06--2024-08-15 - Summer Trip") == ()

    def test_legacy_date_format_day_range(self) -> None:
        issues = check_album_naming("2024-06-15-17 - Weekend")
        codes = [i.code for i in issues]
        assert "invalid-date-format" in codes

    def test_invalid_tag(self) -> None:
        issues = check_album_naming("2024-06-15 - Beach Day [hiking]")
        codes = [i.code for i in issues]
        assert "invalid-tag" in codes

    def test_invalid_tag_format_not_kebab(self) -> None:
        issues = check_album_naming("2024-06-15 - Beach Day [My Tag]")
        codes = [i.code for i in issues]
        assert "invalid-tag-format" in codes

    def test_non_canonical_spacing(self) -> None:
        # This would parse but reconstruct differently if there were
        # extra dashes in the title — but spacing normalization is handled
        # by the parse/reconstruct roundtrip
        issues = check_album_naming("2024-06-15 - Trip - Sub - Title")
        codes = [i.code for i in issues]
        assert "non-canonical-spacing" in codes

    def test_parenthesized_content_is_fine(self) -> None:
        assert check_album_naming("2024-06-15 - Beach Day (bis)") == ()
        assert check_album_naming("2024-06-15 - Hiking (Day 2)") == ()

    def test_name_too_long(self) -> None:
        long_title = "A" * 250
        name = f"2024-06-15 - {long_title}"
        issues = check_album_naming(name)
        codes = [i.code for i in issues]
        assert "name-too-long" in codes

    def test_valid_with_location(self) -> None:
        assert check_album_naming("2024-06-15 - Beach Day @ Malibu, CA") == ()

    def test_valid_with_all_fields(self) -> None:
        assert (
            check_album_naming(
                "2024-06-15 - 01 - Rockies - Hike @ Banff NP, AB, CA [private]"
            )
            == ()
        )

    def test_name_within_limit(self) -> None:
        # 255 bytes exactly (date + separator + title)
        title = "A" * (255 - len("2024-06-15 - "))
        name = f"2024-06-15 - {title}"
        assert len(name.encode("utf-8")) == 255
        issues = check_album_naming(name)
        codes = [i.code for i in issues]
        assert "name-too-long" not in codes

    def test_part_with_day_date_is_valid(self) -> None:
        assert check_album_naming("2024-06-15 - 01 - Morning Walk") == ()

    def test_part_with_year_date_is_invalid(self) -> None:
        issues = check_album_naming("2024 - 01 - Year Album")
        codes = [i.code for i in issues]
        assert "part-requires-day-date" in codes

    def test_part_with_month_date_is_invalid(self) -> None:
        issues = check_album_naming("2024-06 - 01 - Summer")
        codes = [i.code for i in issues]
        assert "part-requires-day-date" in codes

    def test_part_with_day_range_is_invalid(self) -> None:
        issues = check_album_naming("2024-06-15--2024-06-20 - 01 - Road Trip")
        codes = [i.code for i in issues]
        assert "part-requires-day-date" in codes

    def test_part_with_year_range_is_invalid(self) -> None:
        issues = check_album_naming("2023--2024 - 01 - Two Years")
        codes = [i.code for i in issues]
        assert "part-requires-day-date" in codes

    def test_part_with_mixed_range_is_invalid(self) -> None:
        issues = check_album_naming("2024-06--2024-08-15 - 01 - Summer Trip")
        codes = [i.code for i in issues]
        assert "part-requires-day-date" in codes


# ---------------------------------------------------------------------------
# _timestamp_matches_album_date
# ---------------------------------------------------------------------------


class TestTimestampMatchesAlbumDate:
    def test_exact_match(self) -> None:
        ts = datetime(2024, 6, 15, 10, 30)
        assert _timestamp_matches_album_date(ts, "2024-06-15") is True

    def test_within_tolerance(self) -> None:
        ts = datetime(2024, 6, 16, 1, 0)  # next day, 1am
        assert _timestamp_matches_album_date(ts, "2024-06-15", tolerance_days=1) is True

    def test_outside_tolerance(self) -> None:
        ts = datetime(2024, 6, 18, 10, 0)  # 3 days later
        assert (
            _timestamp_matches_album_date(ts, "2024-06-15", tolerance_days=1) is False
        )

    def test_date_range_within(self) -> None:
        ts = datetime(2024, 6, 18, 12, 0)
        assert _timestamp_matches_album_date(ts, "2024-06-15--2024-06-20") is True

    def test_date_range_outside(self) -> None:
        ts = datetime(2024, 7, 1, 12, 0)
        assert (
            _timestamp_matches_album_date(
                ts, "2024-06-15--2024-06-20", tolerance_days=1
            )
            is False
        )

    def test_date_range_tolerance_at_boundary(self) -> None:
        ts = datetime(2024, 6, 14, 23, 0)  # day before start
        assert (
            _timestamp_matches_album_date(
                ts, "2024-06-15--2024-06-20", tolerance_days=1
            )
            is True
        )

    def test_year_only_matches_any_day_in_year(self) -> None:
        assert (
            _timestamp_matches_album_date(datetime(2024, 7, 15, 10, 0), "2024") is True
        )
        assert (
            _timestamp_matches_album_date(
                datetime(2025, 1, 1, 0, 0), "2024", tolerance_days=1
            )
            is True
        )
        assert (
            _timestamp_matches_album_date(
                datetime(2025, 1, 3, 0, 0), "2024", tolerance_days=1
            )
            is False
        )

    def test_month_only_matches_any_day_in_month(self) -> None:
        assert (
            _timestamp_matches_album_date(datetime(2024, 6, 20, 10, 0), "2024-06")
            is True
        )
        assert (
            _timestamp_matches_album_date(
                datetime(2024, 7, 5, 10, 0), "2024-06", tolerance_days=1
            )
            is False
        )


# ---------------------------------------------------------------------------
# _album_date_range
# ---------------------------------------------------------------------------


class TestAlbumDateRange:
    def test_single_date(self) -> None:
        from datetime import date as d

        result = _album_date_range("2024-06-15")
        assert result == (d(2024, 6, 15), d(2024, 6, 15))

    def test_date_range(self) -> None:
        from datetime import date as d

        result = _album_date_range("2024-06-15--2024-06-20")
        assert result == (d(2024, 6, 15), d(2024, 6, 20))

    def test_year_only(self) -> None:
        from datetime import date as d

        result = _album_date_range("2024")
        assert result == (d(2024, 1, 1), d(2024, 12, 31))

    def test_year_month(self) -> None:
        from datetime import date as d

        result = _album_date_range("2024-02")
        assert result == (d(2024, 2, 1), d(2024, 2, 29))  # 2024 is a leap year

    def test_mixed_precision_range(self) -> None:
        from datetime import date as d

        result = _album_date_range("2024-06--2024-08-15")
        assert result == (d(2024, 6, 1), d(2024, 8, 15))

    def test_year_range(self) -> None:
        from datetime import date as d

        result = _album_date_range("2023--2024")
        assert result == (d(2023, 1, 1), d(2024, 12, 31))

    def test_invalid_returns_none(self) -> None:
        assert _album_date_range("not-a-date") is None


# ---------------------------------------------------------------------------
# check_batch_date_collisions
# ---------------------------------------------------------------------------


class TestCheckBatchDateCollisions:
    def test_no_collisions(self) -> None:
        albums = [
            (
                "2024-06-15 - Beach",
                ParsedAlbumName(
                    date="2024-06-15",
                    part="01",
                    private=False,
                    series=None,
                    title="Beach",
                    location=None,
                ),
            ),
            (
                "2024-06-15 - Walk",
                ParsedAlbumName(
                    date="2024-06-15",
                    part="02",
                    private=False,
                    series=None,
                    title="Walk",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is True

    def test_collision_detected(self) -> None:
        albums = [
            (
                "2024-06-15 - Beach",
                ParsedAlbumName(
                    date="2024-06-15",
                    part=None,
                    private=False,
                    series=None,
                    title="Beach",
                    location=None,
                ),
            ),
            (
                "2024-06-15 - Walk",
                ParsedAlbumName(
                    date="2024-06-15",
                    part=None,
                    private=False,
                    series=None,
                    title="Walk",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is False
        assert len(result.date_collisions) == 1
        assert result.date_collisions[0][0] == "2024-06-15"

    def test_private_albums_excluded(self) -> None:
        albums = [
            (
                "2024-06-15 - Beach",
                ParsedAlbumName(
                    date="2024-06-15",
                    part=None,
                    private=False,
                    series=None,
                    title="Beach",
                    location=None,
                ),
            ),
            (
                "2024-06-15 - Beach [private]",
                ParsedAlbumName(
                    date="2024-06-15",
                    part=None,
                    private=True,
                    series=None,
                    title="Beach",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is True

    def test_mixed_parted_and_unparted(self) -> None:
        albums = [
            (
                "2024-06-15 - 01 - Beach",
                ParsedAlbumName(
                    date="2024-06-15",
                    part="01",
                    private=False,
                    series=None,
                    title="Beach",
                    location=None,
                ),
            ),
            (
                "2024-06-15 - Walk",
                ParsedAlbumName(
                    date="2024-06-15",
                    part=None,
                    private=False,
                    series=None,
                    title="Walk",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is False

    def test_single_album_no_collision(self) -> None:
        albums = [
            (
                "2024-06-15 - Beach",
                ParsedAlbumName(
                    date="2024-06-15",
                    part=None,
                    private=False,
                    series=None,
                    title="Beach",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is True

    def test_date_ranges_excluded_from_collisions(self) -> None:
        albums = [
            (
                "2024-06-15--2024-06-20 - Trip A",
                ParsedAlbumName(
                    date="2024-06-15--2024-06-20",
                    part=None,
                    private=False,
                    series=None,
                    title="Trip A",
                    location=None,
                ),
            ),
            (
                "2024-06-15--2024-06-20 - Trip B",
                ParsedAlbumName(
                    date="2024-06-15--2024-06-20",
                    part=None,
                    private=False,
                    series=None,
                    title="Trip B",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is True

    def test_year_and_month_dates_excluded_from_collisions(self) -> None:
        albums = [
            (
                "2024 - Album A",
                ParsedAlbumName(
                    date="2024",
                    part=None,
                    private=False,
                    series=None,
                    title="Album A",
                    location=None,
                ),
            ),
            (
                "2024 - Album B",
                ParsedAlbumName(
                    date="2024",
                    part=None,
                    private=False,
                    series=None,
                    title="Album B",
                    location=None,
                ),
            ),
        ]
        result = check_batch_date_collisions(albums)
        assert result.success is True
