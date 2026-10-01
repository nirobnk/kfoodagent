"""Token and cost bookkeeping: what each reply cost, kept the way OpenAI bills it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage

import crm
from agent.usage import TokenUsage


def openai_reply(prompt: int, cached: int, written: int, completion: int) -> AIMessage:
    return AIMessage(
        content="hi",
        response_metadata={
            "model_name": "gpt-5.6-terra",
            "token_usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "prompt_tokens_details": {"cached_tokens": cached, "cache_write_tokens": written},
            },
        },
    )


def test_usage_adds_up_every_call_in_a_turn():
    usage = TokenUsage()
    usage.add(openai_reply(prompt=7000, cached=0, written=7000, completion=40))
    usage.add(openai_reply(prompt=8600, cached=7000, written=1600, completion=60))

    assert usage.calls == 2
    assert usage.model == "gpt-5.6-terra"
    assert usage.input_tokens == 15600
    assert usage.cached_tokens == 7000
    assert usage.cache_write_tokens == 8600
    assert usage.uncached_tokens == 0
    assert usage.output_tokens == 100


def test_cost_matches_the_openai_bill_for_sept_30():
    """1.1M cache reads, 541.8K cache writes and ~11.4K output tokens came to
    $0.215 + $1.355 + $0.137 on the dashboard."""
    usage = TokenUsage(
        input_tokens=1_641_800, cached_tokens=1_100_000, cache_write_tokens=541_800,
        output_tokens=11_400,
    )

    assert round(usage.cost_usd(), 2) == round(0.22 + 1.3545 + 0.1368, 2)


def test_a_provider_that_reports_nothing_costs_nothing():
    usage = TokenUsage()
    usage.add(AIMessage(content="hi"))

    assert usage.calls == 1
    assert usage.cost_usd() == 0


NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def at(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_agent_costs_per_reply_chat_and_order():
    usage = [
        {"contact_id": "c1", "cost_usd": 0.02, "calls": 2, "input_tokens": 9000, "created_at": at(1)},
        {"contact_id": "c1", "cost_usd": 0.01, "calls": 1, "input_tokens": 7000, "created_at": at(1)},
        {"contact_id": "c2", "cost_usd": 0.03, "calls": 2, "input_tokens": 9000, "created_at": at(2)},
        {"contact_id": "c3", "cost_usd": 9.99, "calls": 1, "created_at": at(40)},
    ]
    orders = [
        {"contact_id": "c1", "source": "agent", "status": "new", "total": 4150, "created_at": at(1)},
        {"contact_id": "c9", "source": "pos", "status": "new", "total": 900, "created_at": at(1)},
    ]

    cost = crm.agent_costs(usage, orders, days=30, now=NOW)

    assert cost["cost_usd"] == 0.06, "a reply outside the window is not counted"
    assert cost["replies"] == 3
    assert cost["model_calls"] == 5
    assert cost["chats"] == 2
    assert cost["per_reply_usd"] == 0.02
    assert cost["per_chat_usd"] == 0.03
    assert cost["orders"] == 1, "counter sales are not the agent's"
    assert cost["per_order_usd"] == 0.06


def test_an_ad_carries_the_cost_of_the_chats_it_brought():
    referrals = [{"contact_id": "c1", "source_id": "A", "headline": "Ad A", "created_at": at(3)}]
    usage = [
        {"contact_id": "c1", "cost_usd": 0.02, "created_at": at(2)},
        {"contact_id": "c1", "cost_usd": 0.05, "created_at": at(4)},   # before the tap
        {"contact_id": "c2", "cost_usd": 0.50, "created_at": at(2)},   # never tapped
    ]

    [ad] = crm.ad_performance(referrals, [], usage=usage, days=30, now=NOW)

    assert ad["agent_cost_usd"] == 0.02
