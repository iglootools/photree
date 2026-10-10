"""Tests for photree.dates — the date grammar shared by albums and collections."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from photree.dates import (
    DATE_PREFIX_RE,
    DatePrefixError,
    DatePrefixKind,
    InvalidDateError,
    date_range,
    is_day_precision,
    is_valid_date,
    parse_month_prefix,
    parse_year_prefix,
    range_contains,
    ranges_overlap,
    timestamp_in_range,
    timestamp_on_day,
)

# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------


class TestDatePrefixRe:
    @pytest.mark.parametrize(
        ("name", "spec"),
        [
            ("2024 - Family", "2024"),
            ("2024-07 - Summer", "2024-07"),
            ("2024-07-14 - Hike", "2024-07-14"),
            ("2024--2025 - Abroad", "2024--2025"),
            ("2024-07--2024-08-03 - Mixed", "2024-07--2024-08-03"),
        ],
    )
    def test_matches_every_precision(self, name: str, spec: str) -> None:
        m = DATE_PREFIX_RE.match(name)
        assert m is not None
        assert m.group(1) == spec

    @pytest.mark.parametrize("name", ["Best of", "2024-07-14", "20245 - Typo"])
    def test_rejects_names_without_prefix(self, name: str) -> None:
        assert DATE_PREFIX_RE.match(name) is None


class TestIsDayPrecision:
    def test_day(self) -> None:
        assert is_day_precision("2024-07-14") is True

    @pytest.mark.parametrize("spec", ["2024", "2024-07", "2024-07-14--2024-07-15"])
    def test_not_day(self, spec: str) -> None:
        assert is_day_precision(spec) is False


# ---------------------------------------------------------------------------
# Ranges
# ---------------------------------------------------------------------------


class TestDateRange:
    def test_single_date(self) -> None:
        result = date_range("2024-06-15")
        assert result == (date(2024, 6, 15), date(2024, 6, 15))

    def test_date_range(self) -> None:
        result = date_range("2024-06-15--2024-06-20")
        assert result == (date(2024, 6, 15), date(2024, 6, 20))

    def test_year_only(self) -> None:
        result = date_range("2024")
        assert result == (date(2024, 1, 1), date(2024, 12, 31))

    def test_year_month(self) -> None:
        result = date_range("2024-02")
        assert result == (date(2024, 2, 1), date(2024, 2, 29))  # 2024 is a leap year

    def test_mixed_precision_range(self) -> None:
        result = date_range("2024-06--2024-08-15")
        assert result == (date(2024, 6, 1), date(2024, 8, 15))

    def test_year_range(self) -> None:
        result = date_range("2023--2024")
        assert result == (date(2023, 1, 1), date(2024, 12, 31))

    def test_invalid_returns_none(self) -> None:
        assert date_range("not-a-date") is None


class TestIsValidDate:
    @pytest.mark.parametrize("spec", ["2024-02-29", "2024-07--2024-08-03", "2024"])
    def test_valid(self, spec: str) -> None:
        assert is_valid_date(spec) is True

    @pytest.mark.parametrize(
        "spec", ["2024-13-45", "2024-02-30", "2024-13", "2024-08--2024-07"]
    )
    def test_invalid(self, spec: str) -> None:
        assert is_valid_date(spec) is False


class TestRangeContains:
    outer = (date(2024, 7, 1), date(2024, 7, 31))

    def test_inside(self) -> None:
        assert range_contains(self.outer, (date(2024, 7, 10), date(2024, 7, 12)))

    def test_same_range(self) -> None:
        assert range_contains(self.outer, self.outer)

    def test_overlap_is_not_containment(self) -> None:
        assert not range_contains(self.outer, (date(2024, 7, 30), date(2024, 8, 2)))


class TestRangesOverlap:
    def test_shared_boundary_day_overlaps(self) -> None:
        assert ranges_overlap(
            (date(2019, 1, 1), date(2019, 6, 30)),
            (date(2019, 6, 30), date(2019, 12, 31)),
        )

    def test_adjacent_ranges_do_not_overlap(self) -> None:
        assert not ranges_overlap(
            (date(2019, 1, 1), date(2019, 6, 29)),
            (date(2019, 6, 30), date(2019, 12, 31)),
        )


# ---------------------------------------------------------------------------
# timestamp_in_range / timestamp_on_day
# ---------------------------------------------------------------------------


class TestTimestampInRange:
    # --- Single day ---

    def test_exact_match(self) -> None:
        assert timestamp_in_range(datetime(2024, 6, 15, 10, 30), "2024-06-15") is True

    def test_next_day_allowed(self) -> None:
        # +1 day tolerance for timezone / midnight crossover
        assert timestamp_in_range(datetime(2024, 6, 16, 1, 0), "2024-06-15") is True

    def test_two_days_later_rejected(self) -> None:
        # +2 days is outside the [album_date, album_date + 2) range
        assert timestamp_in_range(datetime(2024, 6, 17, 0, 0), "2024-06-15") is False

    def test_day_before_rejected(self) -> None:
        assert timestamp_in_range(datetime(2024, 6, 14, 23, 59), "2024-06-15") is False

    # --- Date ranges (exclusive end) ---

    def test_range_within(self) -> None:
        assert (
            timestamp_in_range(datetime(2024, 6, 18, 12, 0), "2024-06-15--2024-06-20")
            is True
        )

    def test_range_last_day(self) -> None:
        # End date is included (exclusive end is end + 1)
        assert (
            timestamp_in_range(datetime(2024, 6, 20, 23, 59), "2024-06-15--2024-06-20")
            is True
        )

    def test_range_day_after_end_rejected(self) -> None:
        assert (
            timestamp_in_range(datetime(2024, 6, 21, 0, 0), "2024-06-15--2024-06-20")
            is False
        )

    def test_range_day_before_start_rejected(self) -> None:
        assert (
            timestamp_in_range(datetime(2024, 6, 14, 23, 59), "2024-06-15--2024-06-20")
            is False
        )

    # --- Year precision ---

    def test_year_any_day(self) -> None:
        assert timestamp_in_range(datetime(2024, 7, 15, 10, 0), "2024") is True

    def test_year_last_day(self) -> None:
        assert timestamp_in_range(datetime(2024, 12, 31, 23, 59), "2024") is True

    def test_year_next_year_rejected(self) -> None:
        # Jan 1 of next year is exclusive
        assert timestamp_in_range(datetime(2025, 1, 1, 0, 0), "2024") is False

    # --- Month precision ---

    def test_month_any_day(self) -> None:
        assert timestamp_in_range(datetime(2024, 6, 20, 10, 0), "2024-06") is True

    def test_month_last_day(self) -> None:
        assert timestamp_in_range(datetime(2024, 6, 30, 23, 59), "2024-06") is True

    def test_month_next_month_rejected(self) -> None:
        assert timestamp_in_range(datetime(2024, 7, 1, 0, 0), "2024-06") is False

    def test_invalid_spec_raises(self) -> None:
        with pytest.raises(InvalidDateError) as exc_info:
            timestamp_in_range(datetime(2024, 2, 28), "2024-02-30")
        assert exc_info.value.spec == "2024-02-30"


class TestTimestampOnDay:
    def test_exact_match(self) -> None:
        assert timestamp_on_day(datetime(2024, 6, 15, 10, 0), "2024-06-15") is True

    def test_next_day_does_not_match(self) -> None:
        assert timestamp_on_day(datetime(2024, 6, 16, 1, 0), "2024-06-15") is False

    def test_non_day_precision_always_true(self) -> None:
        # Only relevant for single-day albums
        assert timestamp_on_day(datetime(2024, 7, 15, 10, 0), "2024") is True
        assert timestamp_on_day(datetime(2024, 7, 15, 10, 0), "2024-06") is True
        assert (
            timestamp_on_day(datetime(2024, 7, 15, 10, 0), "2024-06--2024-08") is True
        )


# ---------------------------------------------------------------------------
# Name prefixes
# ---------------------------------------------------------------------------


class TestParseYearPrefix:
    def test_standard_format(self) -> None:
        assert parse_year_prefix("2024-06-15 - Summer Vacation") == "2024"

    def test_date_only(self) -> None:
        assert parse_year_prefix("2024-06-15") == "2024"

    def test_date_with_underscore_suffix(self) -> None:
        assert parse_year_prefix("2024-01-01_New_Year") == "2024"

    def test_various_years(self) -> None:
        assert parse_year_prefix("2020-12-25 - Christmas") == "2020"
        assert parse_year_prefix("1999-01-01 - Millenium") == "1999"

    def test_no_date_prefix_raises(self) -> None:
        with pytest.raises(DatePrefixError) as exc_info:
            parse_year_prefix("vacation-photos")
        assert exc_info.value.name == "vacation-photos"
        assert exc_info.value.kind == DatePrefixKind.YEAR

    def test_lower_precisions_use_their_year(self) -> None:
        # Year- and month-precision albums are valid names and must be
        # placeable under albums/YYYY/ (gallery import, "albums" share layout).
        assert parse_year_prefix("2024-06") == "2024"
        assert parse_year_prefix("2024 - Family") == "2024"
        assert parse_year_prefix("2024--2025 - Abroad") == "2024"

    def test_five_digit_year_raises(self) -> None:
        with pytest.raises(DatePrefixError):
            parse_year_prefix("20245 - Typo")


class TestParseMonthPrefix:
    def test_standard_format(self) -> None:
        assert parse_month_prefix("2024-06-15 - Summer Vacation") == "2024-06"

    def test_date_only(self) -> None:
        assert parse_month_prefix("2024-06-15") == "2024-06"

    def test_month_precision(self) -> None:
        assert parse_month_prefix("2024-06 - Summer") == "2024-06"

    def test_range_uses_start_month(self) -> None:
        assert parse_month_prefix("2024-06-15--2024-07-17 - Trip") == "2024-06"

    def test_no_date_prefix_raises(self) -> None:
        with pytest.raises(DatePrefixError) as exc_info:
            parse_month_prefix("vacation-photos")
        assert exc_info.value.name == "vacation-photos"
        assert exc_info.value.kind == DatePrefixKind.MONTH

    def test_year_only_raises(self) -> None:
        with pytest.raises(DatePrefixError) as exc_info:
            parse_month_prefix("2024 - Family")
        assert exc_info.value.kind == DatePrefixKind.MONTH
