"""Medication summaries + queries on SYNTHETIC data (tests/conftest.py).

Hand-computed expectations from conftest.MEDICATIONS (placeholder = "Bag";
the blank-name row is excluded everywhere):

  drug            orders  stops  admissions_any  admissions_ordered
  Insulin           4       2         3 (101,102,103)      3
  Heparin           4       4         3 (101,103,104)      2   (104 is stop-only)
  Acetaminophen     8       0         3 (102,103,107)      3
  Warfarin          1       0         1                    1
  *Nf* Warfarin     1       0         1                    1
  Bag (placeholder) 1       0         1                    1

  Admission profile (placeholders excluded): 7 admissions, 6 with events
  (106 has none), 5 with orders (104 has only a stop), 18 orders, 6 stops,
  distinct drugs ordered per admission 3+2+3+1+1 = 10.
"""

import pandas as pd
import pytest

from ehr_analytics.filters import MedicationFilters
from ehr_analytics.repositories import medications as repo

pytestmark = pytest.mark.db

ALL = MedicationFilters()
WITH_PLACEHOLDERS = MedicationFilters(exclude_placeholders=False)


def by(result, key):
    return result.data.set_index(key)


def test_analytics_objects_exist(test_engine):
    assert repo.missing_analytics_objects(test_engine) == []


def test_kpis_exclude_placeholders_by_default(test_engine):
    row = repo.fetch_kpis(test_engine, ALL).data.iloc[0]
    assert row["orders"] == 18
    assert row["stops"] == 6
    assert row["unique_medications"] == 5
    assert row["admissions"] == 7
    assert row["admissions_with_events"] == 6
    assert row["admissions_with_orders"] == 5
    assert row["distinct_drug_orders"] == 10


def test_kpis_can_include_placeholders(test_engine):
    row = repo.fetch_kpis(test_engine, WITH_PLACEHOLDERS).data.iloc[0]
    assert row["orders"] == 19            # + Bag
    assert row["unique_medications"] == 6
    assert row["admissions_with_events"] == 6  # admission profile never counts placeholders


def test_blank_names_never_counted(test_engine):
    names = repo.fetch_drug_options(test_engine, min_admissions=1).data["drug"]
    assert "" not in set(names)


def test_top_medications_rankings(test_engine):
    data = by(repo.fetch_top_medications(test_engine, ALL, min_admissions=1), "drug")
    assert data.loc["Acetaminophen", "rank_by_orders"] == 1
    assert data.loc["Heparin", "orders"] == 4 and data.loc["Heparin", "stops"] == 4
    assert data.loc["Heparin", "admissions_any"] == 3
    assert data.loc["Heparin", "admissions_ordered"] == 2
    assert "Bag" not in data.index
    # Ties on admissions_ordered (3) are broken alphabetically: Acetaminophen, Insulin.
    assert data.loc["Acetaminophen", "rank_by_admissions"] == 1
    assert data.loc["Insulin", "rank_by_admissions"] == 2


def test_top_medications_respects_minimum_admissions(test_engine):
    assert repo.fetch_top_medications(test_engine, ALL).data.empty  # synthetic drugs all < 11


def test_formulations_are_not_merged(test_engine):
    data = by(repo.fetch_top_medications(test_engine, ALL, min_admissions=1), "drug")
    assert data.loc["Warfarin", "orders"] == 1
    assert data.loc["*Nf* Warfarin", "orders"] == 1


def test_filter_by_admission_type(test_engine):
    emer = MedicationFilters.from_selections(admission_types=["EW EMER."])  # 101, 103, 106, 107
    row = repo.fetch_kpis(test_engine, emer).data.iloc[0]
    assert row["admissions"] == 4
    # 101: Insulin 2, Heparin 1, *Nf* Warfarin 1 | 103: Insulin 1, Heparin 3, Acet 1 | 107: Acet 6
    assert row["orders"] == 15


def test_filter_by_age_group(test_engine):
    young = MedicationFilters.from_selections(age_groups=["18–29"])  # patient 1: 101, 102
    row = repo.fetch_kpis(test_engine, young).data.iloc[0]
    assert row["admissions"] == 2
    assert row["orders"] == 4 + 2  # 101 (Bag excluded) + 102


def test_utilization_grouping_sets(test_engine):
    data = repo.fetch_utilization(test_engine, ALL).data
    ages = data[data["dimension"] == "age_group"].set_index("label")
    types = data[data["dimension"] == "admission_type"].set_index("label")
    assert ages["admissions"].sum() == 7 and types["admissions"].sum() == 7
    assert ages.loc["90+ (capped)", "orders"] == 1 + 6  # 105 Warfarin + 107 Acet
    assert types.loc["Not recorded", "admissions_with_orders"] == 0  # 104: stop only


def test_orders_per_admission_bands(test_engine):
    data = by(repo.fetch_orders_per_admission(test_engine, ALL), "orders_bucket")
    assert data.loc[0, "admissions"] == 2   # 104 (stop only) and 106 (none)
    assert data.loc[1, "admissions"] == 5   # 1–9 orders


def test_drug_detail_grouping_sets(test_engine):
    data = repo.fetch_drug_detail(test_engine, ALL, "Insulin").data
    total = data[data["dimension"] == "total"].iloc[0]
    assert total["orders"] == 4 and total["admissions_ordered"] == 3
    assert total["adm_orders_1"] == 2 and total["adm_orders_2"] == 1
    ages = data[data["dimension"] == "age_group"].set_index("label")
    assert ages.loc["18–29", "admissions_ordered"] == 2


def test_drug_detail_unknown_drug_is_empty(test_engine):
    # The name is a bind parameter, so this is just a name that matches nothing.
    # GROUPING SETS (()) still returns one total row, with NULL sums.
    data = repo.fetch_drug_detail(test_engine, ALL, "x'; DROP TABLE medications; --").data
    total = data[data["dimension"] == "total"].iloc[0]
    assert pd.isna(total["admissions_any"])
    assert repo.fetch_kpis(test_engine, ALL).data.iloc[0]["orders"] == 18  # table intact


def test_routes(test_engine):
    data = by(repo.fetch_drug_routes(test_engine, "Acetaminophen"), "route")
    assert data.loc["PO", "orders"] == 7 and data.loc["PO", "admissions"] == 2
    assert data.loc["IV", "orders"] == 1


def test_variants_show_non_formulary_spelling(test_engine):
    data = by(repo.fetch_drug_variants(test_engine, "Warfarin", min_admissions=1), "drug")
    assert data.loc["*Nf* Warfarin", "match_type"] == "same_name"
    assert bool(data.loc["*Nf* Warfarin", "is_non_formulary"])


def test_pairs_and_lift(test_engine):
    pairs = repo.fetch_top_pairs(test_engine, min_admissions=1).data
    lookup = {frozenset((a, b)): row for a, b, row in zip(pairs["drug_a"], pairs["drug_b"], pairs.itertuples())}
    heparin_insulin = lookup[frozenset(("Heparin", "Insulin"))]
    assert heparin_insulin.admissions_both == 2          # admissions 101, 103
    # lift = P(both)/(P(H)P(I)) with 5 admissions having orders: (2/5)/((2/5)(3/5))
    assert heparin_insulin.lift == pytest.approx(5 / 3)
    assert frozenset(("Bag", "Insulin")) not in lookup   # placeholders never paired


def test_partners_rotate_selected_drug(test_engine):
    data = by(repo.fetch_drug_partners(test_engine, "Insulin", min_admissions=1), "partner")
    assert data.loc["Heparin", "admissions_both"] == 2
    assert data.loc["Heparin", "pct_with_partner"] == pytest.approx(2 / 3)  # of 3 Insulin admissions
    assert data.loc["Acetaminophen", "admissions_both"] == 2


def test_co_ordering_matrix_is_directional(test_engine):
    data = repo.fetch_co_ordering_matrix(test_engine).data
    cell = data[(data["row_drug"] == "Heparin") & (data["col_drug"] == "Insulin")].iloc[0]
    reverse = data[(data["row_drug"] == "Insulin") & (data["col_drug"] == "Heparin")].iloc[0]
    assert cell["pct"] == pytest.approx(1.0)       # both Heparin-ordering admissions had Insulin
    assert reverse["pct"] == pytest.approx(2 / 3)  # 2 of 3 Insulin admissions had Heparin


def test_unfiltered_queries_bind_only_their_params(test_engine):
    result = repo.fetch_drug_routes(test_engine, "Insulin")
    assert result.params == {"drug": "Insulin"}
