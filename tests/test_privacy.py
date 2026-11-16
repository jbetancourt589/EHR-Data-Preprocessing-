import math

import pandas as pd
import pytest

from ehr_analytics.privacy import (
    OTHER_LABEL,
    check_cohort,
    format_count,
    is_small,
    protect_categories,
    protect_count_column,
    round_count,
    statistic_allowed,
    suppression_mask,
)


@pytest.mark.parametrize("n, expected", [(0, False), (1, True), (10, True), (11, False), (None, False)])
def test_is_small(n, expected):
    assert is_small(n) is expected


@pytest.mark.parametrize("n, expected", [(12, 10), (13, 15), (15, 15), (491_699, 491_700), (0, 0)])
def test_round_count(n, expected):
    assert round_count(n) == expected


def test_format_count():
    assert format_count(7) == "<11"
    assert format_count(491_699, exact=True) == "491,699"
    assert format_count(491_699) == "491,700"
    assert format_count(None) == "—"


def test_no_suppression_when_all_large():
    assert suppression_mask([100, 50, 20]) == [False, False, False]


def test_single_small_cell_triggers_complementary_suppression():
    # 5 alone could be recovered as total - 100 - 50 - 20; the smallest other
    # cell (20) must also be hidden.
    assert suppression_mask([100, 50, 20, 5]) == [False, False, True, True]


def test_two_small_cells_summing_below_threshold_need_a_third():
    # 3 + 4 = 7 < 11: the pair's sum would still reveal a small group.
    mask = suppression_mask([100, 40, 3, 4])
    assert mask == [False, True, True, True]


def test_two_small_cells_summing_at_threshold_are_enough():
    assert suppression_mask([100, 40, 6, 5]) == [False, False, True, True]


def test_zero_is_not_suppressed_and_not_used_as_complement():
    assert suppression_mask([0, 100, 5, 50]) == [False, False, True, True]


def test_protect_categories_merges_into_other():
    df = pd.DataFrame(
        {"label": ["A", "B", "C", "D"], "admissions": [500, 100, 8, 4], "los_valid_n": [490, 99, 8, 4],
         "median": [2.0, 3.0, 4.0, 5.0]}
    )
    out = protect_categories(df, "label", "admissions", additive_cols=["los_valid_n"])
    assert list(out["label"]) == ["A", "B", OTHER_LABEL]
    other = out[out["is_other"]].iloc[0]
    assert other["admissions"] == 12
    assert other["los_valid_n"] == 12
    assert math.isnan(other["median"])  # statistics cannot be merged


def test_protect_categories_noop_and_empty():
    df = pd.DataFrame({"label": ["A"], "admissions": [50]})
    assert list(protect_categories(df, "label", "admissions")["is_other"]) == [False]
    empty = pd.DataFrame({"label": [], "admissions": []})
    assert protect_categories(empty, "label", "admissions").empty


def test_protect_count_column_rounds_and_hides_only_small_cells():
    out = protect_count_column(pd.Series([123, 7, 52]))
    assert out.iloc[0] == 125
    assert math.isnan(out.iloc[1])
    assert out.iloc[2] == 50  # rounded counts need no complementary hiding


def test_statistic_allowed():
    assert not statistic_allowed(29)
    assert statistic_allowed(30)
    assert not statistic_allowed(None)


def test_check_cohort_rules():
    assert check_cohort(5, 1000, filters_active=False).allowed  # unfiltered: always shown
    assert not check_cohort(5, 1000, filters_active=True).allowed  # too small
    assert not check_cohort(995, 1000, filters_active=True).allowed  # excludes only 5
    assert check_cohort(1000, 1000, filters_active=True).allowed  # excludes nobody
    assert check_cohort(500, 1000, filters_active=True).allowed
