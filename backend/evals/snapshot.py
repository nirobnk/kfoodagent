"""Copy the live catalogue, business profile and FAQs into evals/snapshot.json.

The evals run against this copy, so a result does not change because someone
edited a price, and a run never writes to the real database. Refresh it when
the catalogue changes on purpose, then re-run the evals.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
from config import settings  # noqa: E402

SNAPSHOT = Path(__file__).with_name("snapshot.json")


async def main() -> None:
    client = await db.client.get_db()
    business = await db.business.get(settings.business_id)
    items = (
        await client.table("menu_items").select("*")
        .eq("business_id", settings.business_id).eq("available", True)
        .order("sort_order").execute()
    ).data
    faqs = (
        await client.table("faqs").select("*").eq("business_id", settings.business_id).execute()
    ).data
    snapshot = {
        "business": {"name": business.get("name"), "profile": business.get("profile") or {}},
        "menu_items": [
            {k: v for k, v in row.items() if k not in ("business_id", "created_at", "updated_at")}
            for row in items
        ],
        "faqs": [{"question": f.get("question"), "answer": f.get("answer")} for f in faqs],
    }
    SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, default=str) + "\n")
    print(f"wrote {SNAPSHOT.name}: {len(snapshot['menu_items'])} variants, {len(faqs)} FAQs")


if __name__ == "__main__":
    asyncio.run(main())
