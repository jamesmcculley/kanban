"""Standup mode's pure logic -- see kanban/standup.py."""

from kanban import standup as ST


def test_excluded_ids_permanent_exclusion_has_no_until():
    exclusions = [{"card": "c1", "until": None}]
    assert ST.excluded_ids(exclusions, "2026-09-25") == {"c1"}
    assert ST.excluded_ids(exclusions, "2099-01-01") == {"c1"}


def test_excluded_ids_missing_until_key_also_means_permanent():
    exclusions = [{"card": "c1"}]
    assert ST.excluded_ids(exclusions, "2026-09-25") == {"c1"}


def test_excluded_ids_today_only_applies_on_that_exact_day():
    exclusions = [{"card": "c1", "until": "2026-09-25"}]
    assert ST.excluded_ids(exclusions, "2026-09-25") == {"c1"}
    assert ST.excluded_ids(exclusions, "2026-09-26") == set()


def test_excluded_ids_multiple_entries():
    exclusions = [{"card": "c1", "until": None}, {"card": "c2", "until": "2026-09-25"}]
    assert ST.excluded_ids(exclusions, "2026-09-26") == {"c1"}


def test_clamp_days_default_on_missing_or_unparseable():
    assert ST.clamp_days("", 7) == 7
    assert ST.clamp_days("nope", 7) == 7
    assert ST.clamp_days(None, 7) == 7


def test_clamp_days_zero_is_a_real_value_not_the_default():
    assert ST.clamp_days("0", 7) == 0


def test_clamp_days_negative_clamps_to_zero():
    assert ST.clamp_days("-5", 7) == 0


def test_clamp_days_decimal_is_unparseable_so_falls_back():
    assert ST.clamp_days("3.5", 7) == 7


def test_clamp_days_huge_value_clamps_to_ceiling():
    assert ST.clamp_days("99999999", 7) == ST.MAX_DAYS


def test_clamp_days_strips_whitespace():
    assert ST.clamp_days("  30  ", 7) == 30


def test_clamp_days_accepts_free_text_within_range():
    assert ST.clamp_days("999", 7) == 999
