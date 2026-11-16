import pytest

from ehr_analytics.filters import FILTER_COLUMNS, OverviewFilters, build_where


def test_no_filters_is_true_with_no_params():
    where, params = build_where(OverviewFilters())
    assert where == "TRUE"
    assert params == {}
    assert not OverviewFilters().is_active


def test_single_dimension_uses_any_and_bind_param():
    filters = OverviewFilters.from_selections(admission_types=["URGENT", "ELECTIVE"])
    where, params = build_where(filters)
    assert where == "admission_type = ANY(:admission_types)"
    assert params == {"admission_types": ["ELECTIVE", "URGENT"]}  # sorted
    assert filters.is_active


def test_dimensions_are_and_ed():
    filters = OverviewFilters.from_selections(
        admission_types=["URGENT"], age_groups=["60–69"], discharge_locations=["HOME"]
    )
    where, params = build_where(filters)
    assert where.count(" AND ") == 2
    assert set(params) == {"admission_types", "age_groups", "discharge_locations"}
    assert set(params) <= set(FILTER_COLUMNS)


def test_values_never_enter_sql_text():
    evil = "x'; DROP TABLE admissions; --"
    where, params = build_where(OverviewFilters.from_selections(admission_types=[evil]))
    assert evil not in where
    assert "DROP" not in where
    assert params["admission_types"] == [evil]


def test_selections_are_normalized_for_stable_cache_keys():
    a = OverviewFilters.from_selections(age_groups=["70–79", "18–29", "70–79"])
    b = OverviewFilters.from_selections(age_groups=["18–29", "70–79"])
    assert a == b
    assert hash(a) == hash(b)


def test_non_string_values_rejected():
    with pytest.raises(TypeError):
        OverviewFilters.from_selections(admission_types=[1])


def test_describe():
    assert OverviewFilters().describe() == "All admissions"
    assert "age groups: 60–69" in OverviewFilters.from_selections(age_groups=["60–69"]).describe()
