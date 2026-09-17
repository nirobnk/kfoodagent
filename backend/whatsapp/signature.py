"""Verification of Meta's X-Hub-Signature-256 header."""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    """Return True when `header` is a valid HMAC-SHA256 of `raw_body`.

    An empty app_secret means verification is switched off (local development
    only — config.check_production_readiness() flags it).
    """
    if not app_secret:
        return True
    if not header:
        return False

    header = header.strip()
    if header.startswith("sha256="):
        header = header[len("sha256=") :]

    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.lower())
