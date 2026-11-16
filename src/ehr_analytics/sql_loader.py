"""Load named SQL files from sql/queries/ and render their placeholders.

Placeholders are a deliberately tiny template language:

    {{ base }}   replaced by the contents of <page>/_base.sql
    {{ where }}  replaced by a WHERE expression built by filters.py

Only code-generated SQL from whitelisted fragments is ever substituted;
user-supplied VALUES always travel separately as bind parameters (:name).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

QUERY_DIR = Path(__file__).resolve().parents[2] / "sql" / "queries"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class SqlTemplateError(ValueError):
    """Raised when a query file is missing or a placeholder is left unrendered."""


@lru_cache(maxsize=64)
def read_sql(name: str) -> str:
    """Read sql/queries/<name>.sql, e.g. read_sql("overview/kpis")."""
    if not re.fullmatch(r"[a-z0-9_]+/[a-z0-9_]+", name):
        raise SqlTemplateError(f"Invalid query name: {name!r}")
    path = QUERY_DIR / f"{name}.sql"
    if not path.is_file():
        raise SqlTemplateError(f"Query file not found: {path.relative_to(QUERY_DIR.parent.parent)}")
    return path.read_text(encoding="utf-8")


def render(template: str, **fragments: str) -> str:
    """Replace every {{ key }} with fragments[key]; fail on any unknown key."""

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in fragments:
            raise SqlTemplateError(f"No value supplied for placeholder {{{{ {key} }}}}")
        return fragments[key]

    return _PLACEHOLDER.sub(substitute, template)


def build_page_query(page: str, query: str, where: str, **fragments: str) -> str:
    """Return the full SQL for one page query: base CTE + filters + query body.

    Extra `fragments` (e.g. a second WHERE clause) are substituted into the
    page's _base.sql; like `where`, they must be code-generated from whitelists.
    """
    base = render(read_sql(f"{page}/_base"), where=where, **fragments)
    sql = render(read_sql(f"{page}/{query}"), base=base, where=where, **fragments)
    if _PLACEHOLDER.search(sql):
        raise SqlTemplateError(f"Unrendered placeholder left in {page}/{query}")
    return sql
