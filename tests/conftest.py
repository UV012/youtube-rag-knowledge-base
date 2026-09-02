import os
import pytest

# Guarantee test suite isolation: force LOCAL_DEV=true before any backend code loads
os.environ["LOCAL_DEV"] = "true"

@pytest.fixture(autouse=True, scope="session")
def enforce_test_isolation():
    """Ensure tests run strictly in local in-memory isolation and never touch real Supabase."""
    os.environ["LOCAL_DEV"] = "true"
    yield
