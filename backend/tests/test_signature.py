"""Webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac

from whatsapp.signature import verify_signature

SECRET = "app-secret"
BODY = b'{"object":"whatsapp_business_account"}'


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature():
    assert verify_signature(SECRET, BODY, sign(BODY)) is True


def test_valid_signature_without_prefix():
    assert verify_signature(SECRET, BODY, sign(BODY).split("=", 1)[1]) is True


def test_wrong_signature():
    assert verify_signature(SECRET, BODY, sign(BODY, "other-secret")) is False


def test_tampered_body():
    assert verify_signature(SECRET, b'{"object":"evil"}', sign(BODY)) is False


def test_missing_header_is_rejected():
    assert verify_signature(SECRET, BODY, None) is False
    assert verify_signature(SECRET, BODY, "") is False


def test_no_secret_configured_skips_verification():
    # Local development only; check_production_readiness() flags it.
    assert verify_signature("", BODY, None) is True
