"""The product catalogue — the only source of prices.

K FOOD sells each product in three variants (single / 5 Pack / carton of 20),
so `menu_items` holds one row per variant, grouped by `handle`. The agent
searches products and quotes the exact variant the customer asked for.
"""

from __future__ import annotations

from typing import Any

from .client import get_db, rows

TABLE = "menu_items"

FIELDS = (
    "id,sku,handle,name,product_name,variant_label,units,price,unit_price,brand,"
    "korean_name,category,pack_size,heat_level,cook_time,badge,short_description,"
    "image_url,product_url,available"
)

DETAIL_FIELDS = FIELDS + ",long_description,serving_suggestion,ingredients,allergens,nutrition"

# Characters PostgREST treats as syntax inside an or_() filter.
_UNSAFE = ",*()\"'\\"

# Sri Lankan customers ask for "ramen"; the packs are spelled "ramyun". Without
# this the catalogue silently returns nothing for the most common word of all.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "ramen": ("ramyun", "ramyeon", "noodle"),
    "ramyeon": ("ramyun", "ramen", "noodle"),
    "ramyun": ("ramen", "ramyeon", "noodle"),
    "noodles": ("noodle", "ramyun"),
    "instant": ("instant noodles",),
    "buldak": ("hot dak", "stir fry"),
    "fire": ("hot dak", "super spicy"),
    "spicy": ("spicy", "hot dak", "super spicy"),
    "drink": ("beverages", "milk", "latte"),
    "drinks": ("beverages", "milk", "latte"),
    "juice": ("beverages", "aloe", "latte"),
    "soda": ("beverages", "cream soda", "oncup"),
    "milk": ("binggrae", "milk"),
    "cup": ("cup noodles", "oncup"),
    "energy": ("bacchus",),
    "carton": ("carton",),
}


def expand(term: str) -> list[str]:
    """The search term plus the words Sri Lankan customers use for the same thing."""
    term = term.strip()
    if not term:
        return []
    terms = [term]
    for word in {w.strip("?.,!") for w in term.lower().split()}:
        for synonym in SYNONYMS.get(word, ()):  # noqa: B007
            if synonym not in terms:
                terms.append(synonym)
    return terms


def _clean(term: str) -> str:
    return "".join(" " if c in _UNSAFE else c for c in term).strip()


def group_by_product(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse variant rows into one entry per product, cheapest variant first."""
    products: dict[str, dict[str, Any]] = {}
    for row in variants:
        handle = row.get("handle") or row.get("name")
        product = products.get(handle)
        if product is None:
            product = {
                "handle": handle,
                "product_name": row.get("product_name") or row.get("name"),
                "brand": row.get("brand"),
                "korean_name": row.get("korean_name"),
                "category": row.get("category"),
                "pack_size": row.get("pack_size"),
                "heat_level": row.get("heat_level"),
                "cook_time": row.get("cook_time"),
                "badge": row.get("badge"),
                "description": row.get("short_description"),
                "image_url": row.get("image_url"),
                "product_url": row.get("product_url"),
                "variants": [],
            }
            products[handle] = product
        product["variants"].append(
            {
                "sku": row.get("sku"),
                "label": row.get("variant_label"),
                "price": float(row.get("price") or 0),
                "units": row.get("units") or 1,
                "unit_price": float(row.get("unit_price") or 0),
            }
        )

    for product in products.values():
        product["variants"].sort(key=lambda v: v["price"])
    return list(products.values())


async def list_available(business_id: str, limit: int = 300) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select(FIELDS)
        .eq("business_id", business_id)
        .eq("available", True)
        .order("sort_order")
        .limit(limit)
        .execute()
    )
    return rows(res)


async def search(business_id: str, query: str, limit: int = 60) -> list[dict[str, Any]]:
    """Variant rows matching a free-text query.

    An empty query returns the whole catalogue, which is what the agent wants
    when someone asks "what do you have?".
    """
    term = _clean(query or "")
    if not term:
        return await list_available(business_id, limit=limit)

    db = await get_db()
    columns = ("product_name", "name", "brand", "category", "korean_name", "short_description")
    clause = ",".join(
        f"{column}.ilike.%{candidate}%" for candidate in expand(term) for column in columns
    )
    res = (
        await db.table(TABLE)
        .select(FIELDS)
        .eq("business_id", business_id)
        .eq("available", True)
        .or_(clause)
        .order("sort_order")
        .limit(limit)
        .execute()
    )
    found = rows(res)
    if found:
        return found

    # "spicy noodles" finds nothing as a phrase — try the individual words.
    words = [w for w in term.split() if len(w) > 2][:4]
    if not words:
        return []
    clause = ",".join(
        f"{column}.ilike.%{word}%"
        for word in words
        for column in ("product_name", "brand", "category", "short_description")
    )
    res = (
        await db.table(TABLE)
        .select(FIELDS)
        .eq("business_id", business_id)
        .eq("available", True)
        .or_(clause)
        .order("sort_order")
        .limit(limit)
        .execute()
    )
    return rows(res)


async def search_products(business_id: str, query: str, limit: int = 60) -> list[dict[str, Any]]:
    return group_by_product(await search(business_id, query, limit=limit))


async def get_by_sku(business_id: str, sku: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select(FIELDS)
        .eq("business_id", business_id)
        .eq("sku", sku.strip().upper())
        .limit(1)
        .execute()
    )
    found = rows(res)
    return found[0] if found else None


async def get_by_name(business_id: str, name: str) -> dict[str, Any] | None:
    """Exact variant match, e.g. 'Shin Ramyun Original — 5 Pack'."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select(FIELDS)
        .eq("business_id", business_id)
        .eq("available", True)
        .ilike("name", name.strip())
        .limit(1)
        .execute()
    )
    found = rows(res)
    return found[0] if found else None


async def get_variants(
    business_id: str, product: str, *, by_handle: bool = False
) -> list[dict[str, Any]]:
    """Every variant of one product, matched on handle or product name."""
    db = await get_db()
    query = db.table(TABLE).select(DETAIL_FIELDS).eq("business_id", business_id)
    query = query.eq("handle", product.strip()) if by_handle else query.ilike("product_name", product.strip())
    res = await query.order("price").execute()
    return rows(res)


async def get_product_detail(business_id: str, query: str) -> dict[str, Any] | None:
    """Full detail for one product: allergens, ingredients, how to cook it."""
    variants = await get_variants(business_id, query)
    if not variants:
        matches = await search(business_id, query, limit=6)
        products = group_by_product(matches)
        if not products:
            return None
        variants = await get_variants(business_id, products[0]["handle"], by_handle=True)
        if not variants:
            return None

    first = variants[0]
    product = group_by_product(variants)[0]
    product.update(
        {
            "long_description": first.get("long_description"),
            "serving_suggestion": first.get("serving_suggestion"),
            "ingredients": first.get("ingredients"),
            "allergens": first.get("allergens"),
            "nutrition": first.get("nutrition") or {},
        }
    )
    return product


async def list_categories(business_id: str) -> list[str]:
    items = await list_available(business_id)
    seen: list[str] = []
    for item in items:
        category = item.get("category")
        if category and category not in seen:
            seen.append(category)
    return seen
