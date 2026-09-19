"""Customer arithmetic: turning an order history into something staff can act on.

Pure functions over plain dicts, like `pricing.py`. Nothing here touches the
database or the network, so every rule below is testable by handing it a list of
orders.

Two decisions worth knowing before you read the thresholds:

1. **The scores are absolute, not quintiles.** The textbook RFM model ranks
   customers against each other and calls the top fifth "champions". With a few
   hundred customers, most of whom have ordered once, that hands the crown to
   somebody who bought two packets of ramen and makes the word meaningless.
   These bands are fixed, tuned for a shop selling Rs. 400–900 packets, and
   written in one place so the owner can move them.

2. **Nothing here writes to a contact.** `suggest_lifecycle` returns a
   suggestion; a staff member sets the real one. Orders do not know that a
   customer moved to Dubai, and the CRM should not pretend otherwise.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Orders that never happened do not count towards anything.
CANCELLED = "cancelled"
DELIVERED = "delivered"

LIFECYCLES = ("lead", "active", "regular", "vip", "at_risk", "lost", "blocked")

# --- the bands ------------------------------------------------------------
# (threshold, score), best first. The first row a customer clears is their score.
RECENCY_DAYS = ((14, 5), (30, 4), (60, 3), (120, 2))          # days since last order
FREQUENCY_ORDERS = ((12, 5), (6, 4), (3, 3), (2, 2), (1, 1))  # orders placed
MONETARY_RUPEES = ((50_000, 5), (25_000, 4), (10_000, 3), (4_000, 2), (1, 1))

# The cadence rule. A customer is "quiet" once their silence runs past this
# multiple of their own usual gap between orders — someone who ordered weekly
# and has not been seen for a month is a different problem from someone who
# ordered twice a year and is one month late. The floor stops a customer who
# ordered twice in one afternoon from being declared at risk the next morning.
QUIET_GAP_MULTIPLE = 2.0
QUIET_FLOOR_DAYS = 21


def _money(value: Any) -> float:
    """Numerics arrive from PostgREST as strings often enough to matter."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parsed(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _score(value: float, bands: tuple[tuple[float, int], ...]) -> int:
    for threshold, score in bands:
        if value >= threshold:
            return score
    return 0


@dataclass(slots=True)
class FavouriteItem:
    name: str
    sku: str | None
    quantity: int
    orders: int


@dataclass(slots=True)
class CustomerStats:
    """What the orders say about one customer."""

    orders: int = 0
    cancelled_orders: int = 0
    lifetime_value: float = 0.0
    average_order: float = 0.0
    largest_order: float = 0.0
    items_bought: int = 0
    first_order_at: str | None = None
    last_order_at: str | None = None
    days_since_last_order: int | None = None
    days_as_customer: int | None = None
    average_gap_days: float | None = None
    recency_score: int = 0
    frequency_score: int = 0
    monetary_score: int = 0
    suggested_lifecycle: str = "lead"
    favourites: list[FavouriteItem] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["favourites"] = [asdict(item) for item in self.favourites]
        return data


def favourite_items(orders: Iterable[dict[str, Any]], limit: int = 3) -> list[FavouriteItem]:
    """What this customer keeps coming back for, most-bought first.

    Counted on the line's name rather than its SKU: a POS bill can carry a
    hand-typed line with no SKU at all, and "3x Buldak Carbonara" is still the
    answer to the question staff are asking.
    """
    quantities: Counter[str] = Counter()
    appearances: Counter[str] = Counter()
    skus: dict[str, str | None] = {}

    for order in orders:
        if order.get("status") == CANCELLED:
            continue
        seen: set[str] = set()
        for line in order.get("items") or []:
            if not isinstance(line, dict):
                continue
            name = str(line.get("name") or line.get("product") or "").strip()
            if not name:
                continue
            quantity = int(line.get("quantity") or 0)
            quantities[name] += max(quantity, 0)
            skus.setdefault(name, line.get("sku"))
            if name not in seen:
                appearances[name] += 1
                seen.add(name)

    ranked = quantities.most_common(limit)
    return [
        FavouriteItem(name=name, sku=skus.get(name), quantity=quantity, orders=appearances[name])
        for name, quantity in ranked
        if quantity > 0
    ]


def summarise(orders: Iterable[dict[str, Any]], *, now: datetime | None = None) -> CustomerStats:
    """Roll one customer's orders into the numbers the CRM shows."""
    now = _now(now)
    orders = list(orders)
    counted = [o for o in orders if o.get("status") != CANCELLED]

    stats = CustomerStats(
        orders=len(counted),
        cancelled_orders=len(orders) - len(counted),
        favourites=favourite_items(orders),
    )

    if not counted:
        # A contact who has only ever messaged is a lead, and the zero scores
        # say so: no recency to reward, no money to weigh.
        stats.suggested_lifecycle = "lead"
        return stats

    totals = [_money(o.get("total")) for o in counted]
    stats.lifetime_value = round(sum(totals), 2)
    stats.average_order = round(stats.lifetime_value / len(counted), 2)
    stats.largest_order = round(max(totals), 2)
    stats.items_bought = sum(
        int(line.get("quantity") or 0)
        for o in counted
        for line in (o.get("items") or [])
        if isinstance(line, dict)
    )

    dates = sorted(d for d in (_parsed(o.get("created_at")) for o in counted) if d)
    if dates:
        stats.first_order_at = dates[0].isoformat()
        stats.last_order_at = dates[-1].isoformat()
        stats.days_since_last_order = max(0, (now - dates[-1]).days)
        stats.days_as_customer = max(0, (now - dates[0]).days)
        if len(dates) > 1:
            # How often this customer usually comes back, in days. With one
            # order there is no cadence yet and this stays None.
            stats.average_gap_days = round((dates[-1] - dates[0]).days / (len(dates) - 1), 1)

    stats.frequency_score = _score(stats.orders, FREQUENCY_ORDERS)
    stats.monetary_score = _score(stats.lifetime_value, MONETARY_RUPEES)
    if stats.days_since_last_order is not None:
        # Recency is the one band read backwards: fewer days is better, so the
        # thresholds are ceilings rather than floors.
        stats.recency_score = next(
            (score for days, score in RECENCY_DAYS if stats.days_since_last_order <= days), 1
        )

    stats.suggested_lifecycle = suggest_lifecycle(stats)
    return stats


def has_gone_quiet(stats: CustomerStats) -> bool:
    """Is this customer overdue by their own standards?

    The question a fixed "dormant after 60 days" rule cannot answer. Someone who
    orders every Friday and has not been seen for three weeks is a problem;
    someone who orders once a quarter and is three weeks late is not yet.
    """
    if stats.days_since_last_order is None or stats.average_gap_days is None:
        return False
    overdue_after = max(QUIET_FLOOR_DAYS, stats.average_gap_days * QUIET_GAP_MULTIPLE)
    return stats.days_since_last_order > overdue_after


def suggest_lifecycle(stats: CustomerStats) -> str:
    """Where the orders say this relationship stands.

    Read top to bottom; the first sentence that is true wins. The order matters,
    and the reason it matters is the third rule: a customer who used to order
    every week and has gone quiet is at risk, and that outranks the fact that
    they are still one of the biggest spenders on the list. A CRM that shows
    them as a VIP shows them as fine, and nobody sends the message.
    """
    if stats.orders == 0:
        return "lead"

    recency, frequency, money = stats.recency_score, stats.frequency_score, stats.monetary_score

    if recency <= 1:
        # Four months of silence. Whatever they used to be, they are gone.
        return "lost"
    if recency <= 2:
        # Quiet for two to four months. Worth a message while they still
        # remember us — unless they only ever bought once, in which case there
        # is no relationship to rescue.
        return "at_risk" if frequency >= 2 else "lost"
    if has_gone_quiet(stats):
        return "at_risk"
    if frequency <= 1 and recency <= 3:
        # A single purchase, then a month of nothing. There is no cadence to
        # judge them by, so the band has to do it: this is a lapsing one-timer,
        # which is exactly who a message is worth sending to.
        return "at_risk"
    if frequency >= 4 and money >= 4 and recency >= 4:
        return "vip"
    if frequency >= 3:
        return "regular"
    return "active"


# ---------------------------------------------------------------------------
# Shop-wide analytics
# ---------------------------------------------------------------------------
def within(
    orders: Iterable[dict[str, Any]], *, days: int, now: datetime | None = None
) -> list[dict[str, Any]]:
    """The orders placed in the last `days`, newest-first order preserved."""
    cutoff = _now(now) - timedelta(days=days)
    return [
        order
        for order in orders
        if (placed := _parsed(order.get("created_at"))) and placed >= cutoff
    ]


def _day(value: Any) -> str | None:
    parsed = _parsed(value)
    return parsed.date().isoformat() if parsed else None


def revenue_by_day(
    orders: Iterable[dict[str, Any]], *, days: int = 30, now: datetime | None = None
) -> list[dict[str, Any]]:
    """A dense series — every day in the window, including the dead ones.

    Gaps matter here. A chart that silently skips the days nobody ordered draws
    a busy week where there was a quiet fortnight.
    """
    now = _now(now)
    start = (now - timedelta(days=days - 1)).date()
    buckets: dict[str, dict[str, float]] = {
        (start + timedelta(days=offset)).isoformat(): {"revenue": 0.0, "orders": 0}
        for offset in range(days)
    }

    for order in orders:
        if order.get("status") == CANCELLED:
            continue
        day = _day(order.get("created_at"))
        if day in buckets:
            buckets[day]["revenue"] += _money(order.get("total"))
            buckets[day]["orders"] += 1

    return [
        {"day": day, "revenue": round(value["revenue"], 2), "orders": int(value["orders"])}
        for day, value in sorted(buckets.items())
    ]


def top_products(orders: Iterable[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Best sellers by revenue, with the quantity behind each one."""
    revenue: Counter[str] = Counter()
    quantity: Counter[str] = Counter()

    for order in orders:
        if order.get("status") == CANCELLED:
            continue
        for line in order.get("items") or []:
            if not isinstance(line, dict):
                continue
            name = str(line.get("name") or line.get("product") or "").strip()
            if not name:
                continue
            count = int(line.get("quantity") or 0)
            quantity[name] += count
            # A line without a subtotal is priced from its unit price, and a
            # line with neither contributes quantity but no money rather than
            # dropping out of the ranking entirely.
            subtotal = line.get("subtotal")
            if subtotal is None:
                subtotal = _money(line.get("unit_price")) * count
            revenue[name] += _money(subtotal)

    return [
        {"name": name, "revenue": round(amount, 2), "quantity": quantity[name]}
        for name, amount in revenue.most_common(limit)
    ]


def mix(orders: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """How orders split across a column — status, or which till took them."""
    counts: Counter[str] = Counter()
    money: Counter[str] = Counter()
    for order in orders:
        bucket = str(order.get(key) or "unknown")
        counts[bucket] += 1
        if order.get("status") != CANCELLED:
            money[bucket] += _money(order.get("total"))
    return [
        {"key": bucket, "orders": count, "revenue": round(money[bucket], 2)}
        for bucket, count in counts.most_common()
    ]


def new_versus_returning(
    orders: Iterable[dict[str, Any]], *, days: int = 30, now: datetime | None = None
) -> dict[str, Any]:
    """Of the customers who ordered in the window, how many were already ours.

    "First order" is judged against the whole history passed in, so hand this
    every order you have rather than only the window — otherwise everyone looks
    new.
    """
    now = _now(now)
    cutoff = now - timedelta(days=days)
    counted = [o for o in orders if o.get("status") != CANCELLED]

    first_order: dict[str, datetime] = {}
    for order in counted:
        contact = str(order.get("contact_id") or "")
        placed = _parsed(order.get("created_at"))
        if not contact or not placed:
            continue
        if contact not in first_order or placed < first_order[contact]:
            first_order[contact] = placed

    new_ids, returning_ids = set(), set()
    new_revenue = returning_revenue = 0.0
    for order in counted:
        contact = str(order.get("contact_id") or "")
        placed = _parsed(order.get("created_at"))
        if not contact or not placed or placed < cutoff:
            continue
        if first_order.get(contact) == placed:
            new_ids.add(contact)
            new_revenue += _money(order.get("total"))
        else:
            returning_ids.add(contact)
            returning_revenue += _money(order.get("total"))

    # A customer whose first order was in the window and who came back inside it
    # is counted once, as new. Otherwise the two numbers add up to more
    # customers than the shop has.
    returning_ids -= new_ids

    return {
        "days": days,
        "new_customers": len(new_ids),
        "returning_customers": len(returning_ids),
        "new_revenue": round(new_revenue, 2),
        "returning_revenue": round(returning_revenue, 2),
    }


def totals(
    orders: Iterable[dict[str, Any]], *, days: int = 30, now: datetime | None = None
) -> dict[str, Any]:
    """Headline figures for the window, each with the period before it to compare."""
    now = _now(now)
    window_start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)

    def measure(rows: list[dict[str, Any]]) -> dict[str, Any]:
        live = [o for o in rows if o.get("status") != CANCELLED]
        revenue = sum(_money(o.get("total")) for o in live)
        return {
            "orders": len(live),
            "revenue": round(revenue, 2),
            "average_order": round(revenue / len(live), 2) if live else 0.0,
            "customers": len({str(o.get("contact_id")) for o in live if o.get("contact_id")}),
            "cancelled": len(rows) - len(live),
        }

    current_rows, previous_rows = [], []
    for order in orders:
        placed = _parsed(order.get("created_at"))
        if not placed:
            continue
        if placed >= window_start:
            current_rows.append(order)
        elif placed >= previous_start:
            previous_rows.append(order)

    return {"days": days, "current": measure(current_rows), "previous": measure(previous_rows)}
