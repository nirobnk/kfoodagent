"""Questions the website already answers, so WhatsApp answers them the same way."""

from __future__ import annotations

from typing import Any

from .client import get_db, rows

TABLE = "faqs"


async def list_all(business_id: str, limit: int = 50) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("question,answer,tags")
        .eq("business_id", business_id)
        .order("sort_order")
        .limit(limit)
        .execute()
    )
    return rows(res)


async def search(business_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Word-overlap search. The FAQ list is tiny, so this runs in memory."""
    entries = await list_all(business_id)
    term = (query or "").lower().strip()
    if not term:
        return entries[:limit]

    stop = {"the", "and", "for", "you", "your", "are", "can", "does", "how", "what", "with", "from"}
    words = {w.strip("?.,!") for w in term.split() if len(w) > 2} - stop

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        haystack = f"{entry['question']} {entry['answer']}".lower()
        score = sum(1 for word in words if word in haystack)
        if entry["question"].lower() in term or term in entry["question"].lower():
            score += 3
        if score:
            scored.append((score, entry))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]
