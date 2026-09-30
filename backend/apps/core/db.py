"""ORM helpers that keep queries honest.

``select_related``/``prefetch_related`` discipline is easy to lose as a codebase
grows, so querysets used by list endpoints live in one auditable place.
"""

from __future__ import annotations

from django.db import connection, reset_queries
from typing import Any


class QueryCounter:  # pragma: no cover - test utility
    """Context manager that asserts a code block stays under an N+1 budget.

    Used in tests to prove views are not fanning out per-row queries::

        with QueryCounter(limit=8):
            response = client.get("/api/v1/courses/")

    If ``limit`` is exceeded an :class:`AssertionError` names the offending SQL.
    """

    def __init__(self, limit: int = 10) -> None:
        self.limit = limit
        self.queries: list[dict[str, Any]] = []

    def __enter__(self) -> "QueryCounter":
        reset_queries()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.queries = list(connection.queries)
        if exc_type is not None:
            return False
        if len(self.queries) > self.limit:
            joined = "\n".join(q["sql"] for q in self.queries[: self.limit + 5])
            raise AssertionError(
                f"Query budget exceeded: {len(self.queries)} queries > limit "
                f"{self.limit}.\nFirst queries:\n{joined}"
            )
        return False
