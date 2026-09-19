"""Phone normalisation.

Staff type a number the way it is written on a parcel; Meta identifies the same
customer as 94771234567. If those diverge, one customer becomes two contact rows
and neither can see their own order history — a failure that is invisible until
someone wonders why a regular has no past orders.
"""

from __future__ import annotations

import pytest

from phones import InvalidPhone, to_local, to_wa_id


@pytest.mark.parametrize(
    "written",
    [
        "0771234567",
        "077 123 4567",
        "077-123-4567",
        "+94771234567",
        "+94 77 123 4567",
        "94771234567",
        "0094771234567",
        "(077) 123 4567",
        " 0771234567 ",
    ],
)
def test_every_way_a_number_gets_written_is_the_same_customer(written):
    assert to_wa_id(written) == "94771234567"


@pytest.mark.parametrize("junk", ["", None, "hello", "12345", "07712345678901", "94"])
def test_anything_that_is_not_a_number_is_refused(junk):
    """Refusing beats guessing: a junk contact row is invisible until it hurts."""
    with pytest.raises(InvalidPhone):
        to_wa_id(junk)


def test_an_invoice_prints_the_local_form():
    assert to_local("94771234567") == "0771234567"


def test_an_unrecognised_id_prints_unchanged():
    assert to_local("something-else") == "something-else"
    assert to_local(None) == ""
