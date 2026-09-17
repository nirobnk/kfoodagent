"""The graph itself: load_context -> agent -> tools -> agent -> reply.

The LLM is stubbed. What is under test is the wiring: that history and notes
reach the model, that a tool call is executed and fed back, and that exactly one
reply comes out.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage, SystemMessage

import agent.graph as graph_module
import db
from agent.graph import run_agent
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood

CONTACT = {
    "id": "22222222-2222-2222-2222-222222222222",
    "business_id": BUSINESS_ID,
    "wa_id": "94771234567",
    "name": "Nimal",
    "language": "en",
    "tags": [],
    "human_takeover": False,
}


class StubLLM:
    """Replays a scripted sequence of model responses and records its input."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = list(responses)
        self.seen: list[list] = []

    async def ainvoke(self, messages, config=None):
        self.seen.append(list(messages))
        if not self.responses:
            return AIMessage(content="(no more scripted responses)")
        return self.responses.pop(0)


@pytest.fixture
def env(monkeypatch):
    fake = FakeSupabase()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)

    db.business.clear_cache()
    seed_kfood(fake, BUSINESS_ID)
    fake.seed("contacts", [dict(CONTACT)])
    return fake


def install_llm(monkeypatch, responses: list[AIMessage]) -> StubLLM:
    stub = StubLLM(responses)
    monkeypatch.setattr(graph_module, "_llm_with_tools", lambda: stub)
    return stub


async def test_tool_call_is_executed_and_the_answer_comes_back(env, monkeypatch):
    stub = install_llm(
        monkeypatch,
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_menu", "args": {"query": "ramen"}, "id": "call-1"}],
            ),
            AIMessage(content="We have **Shin Ramyun** at Rs. 950 🍜"),
        ],
    )

    reply = await run_agent(
        business_id=BUSINESS_ID, contact=CONTACT, incoming_text="what ramen do you have?"
    )

    assert reply.text == "We have *Shin Ramyun* at Rs. 950 🍜"
    assert reply.tools_called == ["search_menu"]
    assert reply.failed is False

    # The tool result was fed back to the model before it answered.
    second_turn = stub.seen[1]
    assert any("Shin Ramyun" in str(getattr(m, "content", "")) for m in second_turn)


async def test_the_system_prompt_and_history_reach_the_model(env, monkeypatch):
    env.seed(
        "messages",
        [
            {"id": "1", "business_id": BUSINESS_ID, "contact_id": CONTACT["id"],
             "direction": "in", "sender": "customer", "body": "hi", "message_type": "text",
             "created_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
            {"id": "2", "business_id": BUSINESS_ID, "contact_id": CONTACT["id"],
             "direction": "out", "sender": "agent", "body": "Hello! How can I help?",
             "message_type": "text",
             "created_at": (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()},
        ],
    )
    env.seed(
        "notes",
        [{"id": "n1", "business_id": BUSINESS_ID, "contact_id": CONTACT["id"],
          "note": "Allergic to peanuts", "created_by": "agent",
          "created_at": datetime.now(timezone.utc).isoformat()}],
    )
    stub = install_llm(monkeypatch, [AIMessage(content="Sure!")])

    await run_agent(business_id=BUSINESS_ID, contact=CONTACT, incoming_text="one kimbap please")

    first_turn = stub.seen[0]
    system = first_turn[0]
    assert isinstance(system, SystemMessage)
    assert "Allergic to peanuts" in system.content
    assert "Nimal" in system.content
    # Delivery and payment facts come from the seeded business profile.
    assert "Rs. 400" in system.content
    assert "K FOOD" in system.content
    assert "bank transfer" in system.content.lower()

    bodies = [str(getattr(m, "content", "")) for m in first_turn]
    assert "hi" in bodies
    assert "Hello! How can I help?" in bodies
    assert "one kimbap please" in bodies


async def test_the_current_message_is_not_duplicated_when_already_stored(env, monkeypatch):
    env.seed(
        "messages",
        [{"id": "1", "business_id": BUSINESS_ID, "contact_id": CONTACT["id"], "direction": "in",
          "sender": "customer", "body": "one kimbap please", "message_type": "text",
          "created_at": datetime.now(timezone.utc).isoformat()}],
    )
    stub = install_llm(monkeypatch, [AIMessage(content="Sure!")])

    await run_agent(business_id=BUSINESS_ID, contact=CONTACT, incoming_text="one kimbap please")

    bodies = [str(getattr(m, "content", "")) for m in stub.seen[0]]
    assert bodies.count("one kimbap please") == 1


async def test_an_llm_failure_hands_the_chat_to_a_human(env, monkeypatch):
    class Exploding:
        async def ainvoke(self, messages, config=None):
            raise RuntimeError("gemini is down")

    monkeypatch.setattr(graph_module, "_llm_with_tools", lambda: Exploding())

    reply = await run_agent(business_id=BUSINESS_ID, contact=CONTACT, incoming_text="hello")

    assert reply.failed is True
    assert reply.escalated is True
    assert "staff member will reply" in reply.text
    assert env.rows("contacts")[0]["human_takeover"] is True


async def test_an_empty_model_answer_still_produces_a_reply(env, monkeypatch):
    install_llm(monkeypatch, [AIMessage(content="   ")])

    reply = await run_agent(business_id=BUSINESS_ID, contact=CONTACT, incoming_text="hello")

    assert reply.text, "the customer must never get silence from a successful run"


async def test_escalation_inside_a_run_is_reported(env, monkeypatch):
    install_llm(
        monkeypatch,
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "escalate_to_human", "args": {"reason": "wrong order"}, "id": "c1"}
                ],
            ),
            AIMessage(content="Sorry about that — a team member will reply shortly."),
        ],
    )

    reply = await run_agent(business_id=BUSINESS_ID, contact=CONTACT, incoming_text="wrong order!")

    assert reply.escalated is True
    assert reply.escalation_reason == "wrong order"
    assert env.rows("contacts")[0]["human_takeover"] is True


async def test_an_order_created_during_the_run_is_returned(env, monkeypatch):
    install_llm(
        monkeypatch,
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_order",
                        "args": {"items": [{"sku": "RAM-SHIN-5", "quantity": 1}]},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Order placed! Total Rs. 1,900."),
        ],
    )

    reply = await run_agent(business_id=BUSINESS_ID, contact=CONTACT, incoming_text="one 5 pack of shin ramyun")

    assert reply.created_order is not None
    assert reply.created_order["subtotal"] == 3250
    assert reply.created_order["delivery_fee"] == 400   # 3,250 is under the free threshold
    assert reply.created_order["total"] == 3650
    assert env.rows("orders")[0]["status"] == "new"
