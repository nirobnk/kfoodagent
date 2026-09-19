"""Re-pricing a basket from the catalogue.

The rule this module exists to enforce: **a client never decides what something
costs.** The POS sends SKUs and quantities; the price comes from `menu_items`
here, the delivery fee from the business profile, and the total is arithmetic on
those. A stale POS cache, a typo, or a tampered request cannot move money.

This mirrors what `agent/tools/orders.py` already does for the WhatsApp agent.
That code is deliberately left alone for now — it is the most load-bearing path
in the system and is quoted to real customers. Once this has run in production
for a while, the agent tool should be moved onto it.

The one thing that IS trusted from the caller is the price of a custom line: an
item that is not in the catalogue has no other source of truth. Those are always
flagged `custom: true` so a trusted price is never mistaken for a catalogue one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import db

log = logging.getLogger(__name__)

# A line the catalogue has never heard of. The POS generates these for its
# "item not in the list" path.
CUSTOM_SKU_PREFIX = "CUSTOM-"


@dataclass(slots=True)
class Difference:
    """One place the printed paper and the catalogue disagree."""

    name: str
    reason: str                       # price_changed | sku_unknown | totals
    printed_unit_price: float | None = None
    server_unit_price: float | None = None
    sku: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "reason": self.reason,
            "printed_unit_price": self.printed_unit_price,
            "server_unit_price": self.server_unit_price,
        }


@dataclass(slots=True)
class Repriced:
    items: list[dict[str, Any]] = field(default_factory=list)
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    delivery: float = 0.0
    total: float = 0.0
    differences: list[Difference] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return not self.differences

    def totals(self) -> dict[str, float]:
        return {
            "subtotal": self.subtotal,
            "discount": self.discount,
            "tax": self.tax,
            "delivery": self.delivery,
            "total": self.total,
        }


def is_custom(sku: str | None) -> bool:
    return not sku or str(sku).upper().startswith(CUSTOM_SKU_PREFIX)


async def reprice(
    *,
    business_id: str,
    lines: list[Any],
    printed_discount: float = 0.0,
    delivery_override: float | None = None,
) -> Repriced:
    """Price a basket from the catalogue.

    `lines` are objects carrying `sku`, `name`, `variant`, `quantity` and
    `printed_unit_price` (the POS's `PosBillLine`). Returns the server's view of
    the basket plus every way it differs from what was printed.
    """
    result = Repriced()

    for line in lines:
        sku = getattr(line, "sku", None)
        quantity = int(getattr(line, "quantity", 1) or 1)
        printed = float(getattr(line, "printed_unit_price", 0) or 0)
        given_name = (getattr(line, "name", None) or "").strip()
        variant = getattr(line, "variant", None)

        item = None
        if not is_custom(sku):
            item = await db.menu.get_by_sku(business_id, str(sku))

        if item is None:
            # An unknown SKU does NOT reject the bill, and this is the one place
            # the POS must diverge from the agent tool. The agent is deciding
            # whether to sell, so refusing is right. The POS is recording
            # something already printed and already in a customer's parcel —
            # refusing would leave paper with no row in the database anywhere,
            # which is strictly worse than an imperfect row.
            if not is_custom(sku):
                result.differences.append(
                    Difference(
                        sku=str(sku),
                        name=given_name or str(sku),
                        reason="sku_unknown",
                        printed_unit_price=printed,
                        server_unit_price=None,
                    )
                )
            result.items.append(_custom_line(given_name or str(sku or "Item"),
                                             variant, quantity, printed))
            result.subtotal += printed * quantity
            continue

        price = float(item.get("price") or 0)
        if round(price, 2) != round(printed, 2):
            result.differences.append(
                Difference(
                    sku=str(item.get("sku")),
                    name=str(item.get("name") or given_name),
                    reason="price_changed",
                    printed_unit_price=printed,
                    server_unit_price=price,
                )
            )

        line_total = price * quantity
        result.subtotal += line_total
        result.items.append(
            {
                "sku": item.get("sku"),
                # Carried so inventory.sell_order() can find the product when
                # staff later confirm the order. Its absence is what makes a
                # custom line stock-neutral.
                "menu_item_id": item.get("id"),
                "name": item.get("name"),
                "product": item.get("product_name"),
                "variant": item.get("variant_label"),
                "quantity": quantity,
                "unit_price": price,
                "subtotal": round(line_total, 2),
            }
        )

    profile = await db.business.get_profile(business_id)

    # Clamped, never re-derived. The POS already resolved "10%" into rupees and
    # printed that figure; re-deriving a percentage here could contradict paper.
    result.discount = min(max(float(printed_discount or 0), 0.0), result.subtotal)

    # Tax comes from the business profile, never from the device. A money input
    # a till can edit has no business being authoritative. Absent today, so 0.
    tax_rate = float(((profile.get("tax") or {}).get("rate")) or 0)
    result.tax = round((result.subtotal - result.discount) * tax_rate / 100, 2) if tax_rate else 0.0

    if delivery_override is not None:
        result.delivery = max(0.0, float(delivery_override))
    else:
        # On the PRE-discount subtotal, matching pos.js:autoDelivery(t.subtotal)
        # so the two sides agree about when delivery becomes free.
        result.delivery = db.business.delivery_fee_for(profile, result.subtotal)

    result.subtotal = round(result.subtotal, 2)
    # Same ordering as pos.js:totals() — tax on (subtotal - discount), delivery
    # added afterwards and never taxed.
    result.total = round(result.subtotal - result.discount + result.tax + result.delivery)
    return result


def _custom_line(
    name: str, variant: str | None, quantity: int, unit_price: float
) -> dict[str, Any]:
    """A line with no catalogue entry, and therefore no menu_item_id.

    `db.inventory.sell_order()` skips any item lacking `menu_item_id`, so this is
    stock-neutral with no special-casing anywhere.
    """
    return {
        "sku": None,
        "name": name[:120],
        "variant": variant or "Custom item",
        "quantity": quantity,
        "unit_price": round(unit_price, 2),
        "subtotal": round(unit_price * quantity, 2),
        "custom": True,
    }


def compare_totals(
    printed: dict[str, float], server: dict[str, float], *, tolerance: float = 1.0
) -> Difference | None:
    """Whether the two totals disagree by more than rounding.

    Per-line differences are reported separately and always count, even when the
    totals happen to agree — two errors cancelling out is not a match.
    """
    printed_total = float(printed.get("total") or 0)
    server_total = float(server.get("total") or 0)
    if abs(printed_total - server_total) <= tolerance:
        return None
    return Difference(
        name="Bill total",
        reason="totals",
        printed_unit_price=printed_total,
        server_unit_price=server_total,
    )
