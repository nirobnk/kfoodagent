"""Customer memory."""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)


@tool
async def save_note(note: str, config: RunnableConfig) -> str:
    """Remember a lasting fact about this customer for future conversations.

    Good notes: "allergic to peanuts", "never spicy", "orders every Friday",
    "delivers to Nugegoda office". Do not save small talk or one-off requests.

    Args:
        note: One short sentence, written in English.
    """
    ctx = run_context(config)
    ctx.tools_called.append("save_note")

    note = (note or "").strip()
    if len(note) < 3:
        return "Note too short, nothing saved."

    await db.notes.add(
        business_id=ctx.business_id, contact_id=ctx.contact_id, note=note, created_by="agent"
    )
    ctx.notes_added.append(note)
    return "Saved. Do not mention to the customer that you wrote a note."
