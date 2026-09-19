"""Sri Lankan phone numbers in, WhatsApp ids out.

Staff type a number the way it is written on a parcel: 077 123 4567, or
+94 77 123 4567 if they copied it from the chat. Meta identifies the same
customer as 94771234567. One function owns that conversion, because a contact
row created under a second spelling is a second customer who cannot see their
own order history.
"""

from __future__ import annotations

import re

COUNTRY_CODE = "94"

# A local subscriber number is 9 digits after the leading 0 is stripped.
_LOCAL = re.compile(r"^0(\d{9})$")
_INTERNATIONAL = re.compile(r"^94(\d{9})$")


class InvalidPhone(ValueError):
    """The text given is not a Sri Lankan mobile number."""


def to_wa_id(raw: str | None) -> str:
    """Normalise to Meta's form: 94 followed by nine digits.

    Accepts 0771234567, +94 77 123 4567, 94-77-123-4567 and anything else that
    differs only in punctuation. Raises rather than guessing: a junk contact row
    is worse than a rejected bill, because it is invisible until someone wonders
    why a customer has two histories.
    """
    if not raw:
        raise InvalidPhone("no phone number given")

    # Strip everything that is decoration: spaces, dashes, brackets, a leading +.
    digits = re.sub(r"[^\d]", "", str(raw))
    if not digits:
        raise InvalidPhone(f"no digits in {raw!r}")

    # 0094… is how some phones store an international number.
    if digits.startswith("00"):
        digits = digits[2:]

    match = _INTERNATIONAL.match(digits) or _LOCAL.match(digits)
    if match is None:
        raise InvalidPhone(
            f"{raw!r} is not a Sri Lankan mobile number "
            "(expected 0771234567 or +94771234567)"
        )

    return COUNTRY_CODE + match.group(1)


def to_local(wa_id: str | None) -> str:
    """The form a customer recognises, for printing on an invoice."""
    if not wa_id:
        return ""
    digits = re.sub(r"[^\d]", "", str(wa_id))
    if digits.startswith(COUNTRY_CODE) and len(digits) == 11:
        return "0" + digits[2:]
    return str(wa_id)
