"""Translate dashboard filter selections into a parameterized SQL WHERE clause.

Security model
--------------
* Column names come ONLY from the fixed `FILTER_COLUMNS` whitelist below; a
  user can never choose which column or operator is used.
* Selected values never become part of the SQL text. Each dimension produces
  `column = ANY(:param)` and the list of values is sent separately as a bind
  parameter, so a value such as "x'; DROP TABLE admissions; --" is just a
  string that matches nothing.

Semantics
---------
* Within one dimension, selections are OR-ed  (type A or type B).
* Across dimensions, they are AND-ed          (type A and age 60–69).
* An empty selection means "no restriction" (all categories).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterable

# dataclass field name -> column in the page's base CTE (overview: admission_base;
# medications: analytics.med_drug_cell / med_admission_profile)
FILTER_COLUMNS: dict[str, str] = {
    "admission_types": "admission_type",
    "age_groups": "age_group",
    "discharge_locations": "discharge_location",
    "lab_names": "lab_name",
}


def _normalize(values: Iterable[str] | None) -> tuple[str, ...]:
    """Deduplicate and sort so equal selections give equal cache keys."""
    if not values:
        return ()
    cleaned = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("Filter values must be strings")
        cleaned.add(value)
    return tuple(sorted(cleaned))


@dataclass(frozen=True)
class OverviewFilters:
    """Immutable (hashable) filter state for the Hospital Overview page."""

    admission_types: tuple[str, ...] = ()
    age_groups: tuple[str, ...] = ()
    discharge_locations: tuple[str, ...] = ()

    @classmethod
    def from_selections(
        cls,
        admission_types: Iterable[str] | None = None,
        age_groups: Iterable[str] | None = None,
        discharge_locations: Iterable[str] | None = None,
    ) -> "OverviewFilters":
        return cls(
            admission_types=_normalize(admission_types),
            age_groups=_normalize(age_groups),
            discharge_locations=_normalize(discharge_locations),
        )

    @property
    def is_active(self) -> bool:
        """True when at least one dimension restricts the cohort."""
        return any(getattr(self, name) for name in _dimension_fields(self))

    def describe(self) -> str:
        """Human-readable summary, e.g. for captions."""
        return _describe(self)


def _dimension_fields(filters) -> list[str]:
    """Names of the fields that restrict the cohort (tuples of category labels)."""
    return [f.name for f in fields(filters) if f.name in FILTER_COLUMNS]


def _describe(filters) -> str:
    parts = [
        f"{name.replace('_', ' ')}: {', '.join(getattr(filters, name))}"
        for name in _dimension_fields(filters)
        if getattr(filters, name)
    ]
    return "; ".join(parts) if parts else "All admissions"


@dataclass(frozen=True)
class MedicationFilters:
    """Filter state for the Medication Analytics page.

    `exclude_placeholders` is a display option, not a cohort restriction: it
    removes container/order-entry names (Bag, Vial, ...) from medication counts
    but does not change which admissions are in the cohort.
    """

    admission_types: tuple[str, ...] = ()
    age_groups: tuple[str, ...] = ()
    exclude_placeholders: bool = True

    @classmethod
    def from_selections(
        cls,
        admission_types: Iterable[str] | None = None,
        age_groups: Iterable[str] | None = None,
        exclude_placeholders: bool = True,
    ) -> "MedicationFilters":
        return cls(
            admission_types=_normalize(admission_types),
            age_groups=_normalize(age_groups),
            exclude_placeholders=bool(exclude_placeholders),
        )

    @property
    def is_active(self) -> bool:
        """True when a cohort dimension is restricted (the placeholder option is not one)."""
        return bool(self.admission_types or self.age_groups)

    def describe(self) -> str:
        return _describe(self)


def build_where(filters) -> tuple[str, dict[str, list[str]]]:
    """Return (sql_expression, bind_params) for the `filtered` CTE.

    >>> build_where(OverviewFilters.from_selections(age_groups=["60–69"]))
    ('age_group = ANY(:age_groups)', {'age_groups': ['60–69']})
    """
    clauses: list[str] = []
    params: dict[str, list[str]] = {}
    for field_name in _dimension_fields(filters):
        column = FILTER_COLUMNS[field_name]
        values = getattr(filters, field_name)
        if values:
            clauses.append(f"{column} = ANY(:{field_name})")
            params[field_name] = list(values)
    return (" AND ".join(clauses) if clauses else "TRUE"), params


@dataclass(frozen=True)
class LabFilters:
    """Filter state for the Lab Results Analytics page.

    admission_types  cohort restriction (admission category)
    year_from/to     shifted admission-year range; None = no restriction
    lab_names        optional test selection; restricts RESULTS, not the cohort
    """

    admission_types: tuple[str, ...] = ()
    lab_names: tuple[str, ...] = ()
    year_from: int | None = None
    year_to: int | None = None

    @classmethod
    def from_selections(
        cls,
        admission_types: Iterable[str] | None = None,
        lab_names: Iterable[str] | None = None,
        year_range: tuple[int, int] | None = None,
        full_year_range: tuple[int, int] | None = None,
    ) -> "LabFilters":
        """A year range equal to the full available range means "no restriction"."""
        year_from = year_to = None
        if year_range is not None and tuple(year_range) != tuple(full_year_range or ()):
            year_from, year_to = (int(y) for y in sorted(year_range))
        return cls(_normalize(admission_types), _normalize(lab_names), year_from, year_to)

    @property
    def has_year_range(self) -> bool:
        return self.year_from is not None

    @property
    def is_active(self) -> bool:
        """True when the admission cohort is restricted (test selection is not one)."""
        return bool(self.admission_types) or self.has_year_range

    def describe(self) -> str:
        parts = [] if not self.admission_types else [f"admission types: {', '.join(self.admission_types)}"]
        if self.has_year_range:
            parts.append(f"admission years (shifted): {self.year_from}–{self.year_to}")
        if self.lab_names:
            parts.append(f"tests: {', '.join(self.lab_names)}")
        return "; ".join(parts) if parts else "All admissions, all tests"


def build_lab_where(filters: LabFilters) -> tuple[dict[str, str], dict]:
    """Return (fragments, params) for the lab page's SQL templates.

    fragments["where"]         per-test rows: admission type, year range, tests
    fragments["cohort_where"]  admission-level rows (no test column):
                               admission type, year range
    fragments["type_where"]    summaries without a year column (day of stay,
                               histograms): admission type only
    """
    type_where, params = build_where(LabFilters(admission_types=filters.admission_types))
    test_where, test_params = build_where(LabFilters(lab_names=filters.lab_names))
    params = {**params, **test_params}

    def both(a: str, b: str) -> str:
        if a == "TRUE":
            return b
        return a if b == "TRUE" else f"{a} AND {b}"

    cohort_where = type_where
    if filters.has_year_range:
        cohort_where = both(type_where, "admit_year BETWEEN :year_from AND :year_to")
        params.update(year_from=filters.year_from, year_to=filters.year_to)
    fragments = {
        "where": both(cohort_where, test_where),
        "cohort_where": cohort_where,
        "type_where": type_where,
    }
    return fragments, params
