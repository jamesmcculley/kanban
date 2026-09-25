"""Review mode's pure logic -- see kanban/review.py."""

from kanban import review as RV


def test_clamp_days_default_on_missing_or_unparseable():
    assert RV.clamp_days("", 7) == 7
    assert RV.clamp_days("nope", 7) == 7
    assert RV.clamp_days(None, 7) == 7


def test_clamp_days_zero_is_a_real_value_not_the_default():
    assert RV.clamp_days("0", 7) == 0


def test_clamp_days_negative_clamps_to_zero():
    assert RV.clamp_days("-5", 7) == 0


def test_clamp_days_decimal_is_unparseable_so_falls_back():
    assert RV.clamp_days("3.5", 7) == 7


def test_clamp_days_huge_value_clamps_to_ceiling():
    assert RV.clamp_days("99999999", 7) == RV.MAX_DAYS


def test_clamp_days_strips_whitespace():
    assert RV.clamp_days("  30  ", 7) == 30


def test_clamp_days_accepts_free_text_within_range():
    assert RV.clamp_days("999", 7) == 999
