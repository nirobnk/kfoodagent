"""Test environment.

Config is validated at import time, so the fake environment must be in place
before anything imports `config`. No test in this suite touches the network,
Supabase, Meta or an LLM.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.update(
    {
        "WA_ACCESS_TOKEN": "test-token",
        "WA_PHONE_NUMBER_ID": "123456789",
        "WA_BUSINESS_ACCOUNT_ID": "987654321",
        "WA_VERIFY_TOKEN": "verify-token-for-tests",
        "WA_APP_SECRET": "app-secret",
        "WA_API_VERSION": "v26.0",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        "SUPABASE_ANON_KEY": "anon-key",
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-test",
        "GEMINI_API_KEY": "gemini-key",
        "LLM_MODEL": "google/gemini-3.1-flash-lite",
        "BUSINESS_ID": "11111111-1111-1111-1111-111111111111",
        "AUTO_RETURN_MINUTES": "30",
        "ENVIRONMENT": "development",
        "REQUIRE_AUTH": "false",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402

BUSINESS_ID = os.environ["BUSINESS_ID"]


@pytest.fixture
def contact() -> dict:
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "business_id": BUSINESS_ID,
        "wa_id": "94771234567",
        "name": "Nimal",
        "language": "en",
        "tags": [],
        "human_takeover": False,
        "last_customer_message_at": None,
    }


def db_modules() -> tuple:
    """Every module holding a `get_db` reference that tests must redirect."""
    import db

    return (
        db.client,
        db.business,
        db.contacts,
        db.faqs,
        db.menu,
        db.messages,
        db.notes,
        db.orders,
        db.templates,
    )
