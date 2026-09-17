"""Configuration: key resolution and the URL mistake that costs an afternoon."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config import Settings

BASE = {
    "WA_ACCESS_TOKEN": "t",
    "WA_PHONE_NUMBER_ID": "1",
    "WA_VERIFY_TOKEN": "verify-token-x",
    "SUPABASE_URL": "https://abc.supabase.co",
    "BUSINESS_ID": "11111111-1111-1111-1111-111111111111",
}


@pytest.fixture(autouse=True)
def without_ambient_supabase_vars(monkeypatch):
    """conftest exports test values; these tests must see only what they pass."""
    for name in (
        "SUPABASE_SECRET_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_JWKS_URL",
        "SUPABASE_JWT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def build(**overrides) -> Settings:
    values = {**BASE, **overrides}
    # _env_file=None so a developer's real .env cannot influence the test.
    return Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})


def test_new_style_keys_are_used():
    settings = build(SUPABASE_SECRET_KEY="sb_secret_x", SUPABASE_PUBLISHABLE_KEY="sb_publishable_x")

    assert settings.supabase_key == "sb_secret_x"
    assert settings.supabase_client_key == "sb_publishable_x"
    assert settings.uses_legacy_supabase_keys is False


def test_legacy_keys_still_work():
    settings = build(SUPABASE_SERVICE_ROLE_KEY="eyJlegacy", SUPABASE_ANON_KEY="eyJanon")

    assert settings.supabase_key == "eyJlegacy"
    assert settings.supabase_client_key == "eyJanon"
    assert settings.uses_legacy_supabase_keys is True


def test_new_keys_win_over_legacy():
    settings = build(
        SUPABASE_SECRET_KEY="sb_secret_x",
        SUPABASE_SERVICE_ROLE_KEY="eyJlegacy",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_x",
        SUPABASE_ANON_KEY="eyJanon",
    )

    assert settings.supabase_key == "sb_secret_x"
    assert settings.supabase_client_key == "sb_publishable_x"


def test_a_server_key_is_required():
    with pytest.raises(ValidationError, match="SUPABASE_SECRET_KEY"):
        build()


def test_the_rest_url_is_trimmed_back_to_the_project_origin():
    # Pasting the REST URL from the dashboard makes every query 404.
    for given in (
        "https://abc.supabase.co/rest/v1/",
        "https://abc.supabase.co/rest/v1",
        "https://abc.supabase.co/auth/v1",
        "https://abc.supabase.co/",
    ):
        settings = build(SUPABASE_SECRET_KEY="sb_secret_x", SUPABASE_URL=given)
        assert settings.supabase_url == "https://abc.supabase.co"


def test_production_readiness_flags_missing_token_validation():
    settings = build(SUPABASE_SECRET_KEY="sb_secret_x")
    problems = " ".join(settings.check_production_readiness())
    assert "SUPABASE_JWKS_URL" in problems

    settings = build(
        SUPABASE_SECRET_KEY="sb_secret_x",
        SUPABASE_JWKS_URL="https://abc.supabase.co/auth/v1/.well-known/jwks.json",
    )
    assert "SUPABASE_JWKS_URL" not in " ".join(settings.check_production_readiness())
