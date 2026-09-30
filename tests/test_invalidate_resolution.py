import pytest
import datetime
from unittest.mock import MagicMock, patch

from scripts import employer_resolution_lifecycle as mod

def test_invalidate_resolution():
    employer = {
        "id": "example-id",
        "name": "Example Emp",
        "careers_url": "https://careers.example.com",
        "careers_platform": "workday",
        "provider": {"status": "resolved", "family": "workday"}
    }

    mod.invalidate_resolution(employer, "StructuralSourceError")

    assert "careers_url" not in employer
    assert "careers_platform" not in employer
    assert "provider" not in employer
    assert employer["careers_resolution"]["status"] == "unresolved"
    assert employer["careers_resolution"]["attempt_status"] == "invalidated"
    assert employer["careers_resolution"]["evidence"][-1]["type"] == "invalidation"
    assert employer["careers_resolution"]["evidence"][-1]["reason"] == "StructuralSourceError"
