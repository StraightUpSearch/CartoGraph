"""
Conftest for unit tests that do not require a live database.

Overrides the session-scoped `db` autouse fixture from the parent conftest so
that tests in this directory can run without a running PostgreSQL instance.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def db():  # type: ignore[override]
    """No-op override: unit tests don't need a database connection."""
    yield None
