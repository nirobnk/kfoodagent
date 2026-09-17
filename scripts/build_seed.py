#!/usr/bin/env python3
"""Turn the kfoods.lk export into SQL the database can be seeded with.

    python3 scripts/build_seed.py

Reads  data/kfood-catalog.json   (exported from the kfoods.lk static site)
       assets/products/index.json (which products actually have a photo)
Writes supabase/seed_catalog.sql (business profile, 90 product variants, FAQs)

Re-run it whenever the website's catalogue changes; never edit the generated
SQL by hand. Everything is keyed on the business name and every statement is an
upsert, so the file is safe to run more than once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "kfood-catalog.json"
PHOTOS = ROOT / "assets" / "products" / "index.json"
TARGET = ROOT / "supabase" / "seed_catalog.sql"

BUSINESS_NAME = "K FOOD"

PRODUCT_COLUMNS = [
    "sku", "handle", "name", "product_name", "variant_label", "units", "price",
    "unit_price", "brand", "korean_name", "category", "pack_size", "heat_level",
    "cook_time", "badge", "description", "short_description", "long_description",
    "serving_suggestion", "ingredients", "allergens", "nutrition", "image_url",
    "image_file", "product_url", "sort_order", "available",
]


def sql_str(value: Any) -> str:
    """A single-quoted SQL literal, or NULL for anything empty."""
    if value is None or value == "":
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value: Any) -> str:
    return "null" if value is None else str(value)


def sql_json(value: Any) -> str:
    if not value:
        return "'{}'::jsonb"
    return sql_str(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def build_profile(data: dict) -> dict:
    """Everything the agent must know about the business but cannot look up."""
    business = data["site"]["business"]
    catalog = data["catalog"]
    return {
        "trading_name": business["tradingName"],
        "legal_name": business["legalAccountName"],
        "website": business["website"],
        "type": business["type"],
        "currency": business["currency"],
        "price_range": business["priceRange"],
        "area_served": business["areaServed"],
        "authenticity": business["authenticity"],
        "contact": business["contact"],
        "payment": business["payment"],
        "delivery": business["delivery"],
        "returns": business["returnsPolicy"],
        "how_to_order": business["howToOrder"],
        "brands": catalog["brands"],
        "categories": catalog["categories"],
        "source": f"kfoods.lk export {data['meta']['exportedAt']}",
    }


def product_rows(products: list[dict], photos: dict) -> list[str]:
    rows: list[str] = []
    order = 0
    for product in products:
        image_file = (photos.get(product["handle"]) or {}).get("photo")
        # Only claim an image when a real photo exists; the site falls back to a
        # shared "coming soon" placeholder for ten products.
        image_url = product["images"]["main"] if image_file else None

        for variant in product["variants"]:
            order += 1
            values = [
                sql_str(variant["sku"]),
                sql_str(product["handle"]),
                sql_str(f"{product['name']} — {variant['label']}"),
                sql_str(product["name"]),
                sql_str(variant["label"]),
                sql_num(variant["units"]),
                sql_num(variant["price"]),
                sql_num(variant["unitPrice"]),
                sql_str(product["brand"]),
                sql_str(product.get("ko")),
                sql_str(product["category"]),
                sql_str(product.get("pack")),
                sql_num(product.get("heat")),
                sql_str(product.get("cook")),
                sql_str(product.get("badge")),
                sql_str(product.get("short")),
                sql_str(product.get("short")),
                sql_str(product.get("long")),
                sql_str(product.get("serve")),
                sql_str(product.get("ingredients")),
                sql_str(product.get("allergens")),
                sql_json(product.get("nutrition")),
                sql_str(image_url),
                sql_str(image_file),
                sql_str(product.get("url")),
                str(order),
                "true",
            ]
            rows.append("    (" + ", ".join(values) + ")")
    return rows


def faq_rows(faqs: list[dict]) -> list[str]:
    return [
        "    (" + ", ".join([sql_str(faq["question"]), sql_str(faq["answer"]), str(index)]) + ")"
        for index, faq in enumerate(faqs, start=1)
    ]


def build() -> str:
    data = json.loads(SOURCE.read_text())
    photos = json.loads(PHOTOS.read_text())["products"] if PHOTOS.exists() else {}

    products = data["catalog"]["products"]
    faqs = data["site"]["faq"]
    variants = sum(len(p["variants"]) for p in products)
    with_photo = sum(1 for p in products if (photos.get(p["handle"]) or {}).get("photo"))

    updates = ",\n".join(
        f"  {column} = excluded.{column}" for column in PRODUCT_COLUMNS if column != "sku"
    )

    return f"""-- seed_catalog.sql — GENERATED FILE, do not edit by hand.
--
--   source:    data/kfood-catalog.json (exported from the kfoods.lk site)
--   generator: scripts/build_seed.py
--   products:  {len(products)} ({variants} variants, {with_photo} with a real photo)
--   faqs:      {len(faqs)}
--
-- Run after the migrations and after seed.sql has created the business row.
-- Safe to run repeatedly: every statement is an upsert keyed on the business.

-- ---------------------------------------------------------------------------
-- 1. Business profile — delivery, payment, returns, contact, how to order.
--    This is what the agent answers "do you deliver to Kandy?" from.
-- ---------------------------------------------------------------------------
update businesses
   set profile = {sql_json(build_profile(data))}
 where name = {sql_str(BUSINESS_NAME)};

-- ---------------------------------------------------------------------------
-- 2. Products — one row per variant (single / 5 Pack / carton of 20).
--    These prices are the only ones the agent is allowed to quote.
-- ---------------------------------------------------------------------------
insert into menu_items (business_id, {", ".join(PRODUCT_COLUMNS)})
select b.id, {", ".join("v." + column for column in PRODUCT_COLUMNS)}
from businesses b
cross join (values
{",\n".join(product_rows(products, photos))}
) as v({", ".join(PRODUCT_COLUMNS)})
where b.name = {sql_str(BUSINESS_NAME)}
on conflict (business_id, sku) do update set
{updates};

-- ---------------------------------------------------------------------------
-- 3. FAQs — so answers on WhatsApp match answers on the website.
-- ---------------------------------------------------------------------------
insert into faqs (business_id, question, answer, sort_order)
select b.id, v.question, v.answer, v.sort_order
from businesses b
cross join (values
{",\n".join(faq_rows(faqs))}
) as v(question, answer, sort_order)
where b.name = {sql_str(BUSINESS_NAME)}
on conflict (business_id, question) do update set
  answer = excluded.answer,
  sort_order = excluded.sort_order;
"""


if __name__ == "__main__":
    TARGET.write_text(build())
    print(f"wrote {TARGET.relative_to(ROOT)}")
