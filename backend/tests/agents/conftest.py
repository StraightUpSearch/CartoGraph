"""
Conftest for agent unit tests — no database required.
Overrides the session-scoped autouse `db` fixture from the parent conftest.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def db():  # type: ignore[override]
    """No-op override: agent tests don't need a database connection."""
    yield None
