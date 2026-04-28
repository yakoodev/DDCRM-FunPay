from __future__ import annotations

import pytest

from ddcrm_funpay_worker.models import validate_marketplace_auth


def test_validate_marketplace_auth_accepts_golden_key() -> None:
    validate_marketplace_auth("golden_key", {"golden_key": "secret"})


def test_validate_marketplace_auth_rejects_unknown_scheme() -> None:
    with pytest.raises(ValueError):
        validate_marketplace_auth("unknown_scheme", {"a": "b"})


def test_validate_marketplace_auth_requires_golden_key_value() -> None:
    with pytest.raises(ValueError):
        validate_marketplace_auth("golden_key", {"user_agent": "ua"})
