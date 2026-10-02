"""Replay the real conversations in cases.py against the agent and score them.

Everything runs in memory from snapshot.json — the real model is called, but
Supabase and WhatsApp never are. See evals/__init__.py for how to run it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
from agent import run_agent  # noqa: E402
from agent.usage import TokenUsage  # noqa: E402
from config import settings  # noqa: E402
from evals.cases import CASES  # noqa: E402
from fastpath import fast_reply  # noqa: E402
from tests.fakes import FakeSupabase  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# Dollars per million tokens: input, cached input, cache write, output.
PRICES = {
    "gpt-5.6-terra": (2.00, 0.20, 2.50, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 0.25, 1.20),
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
}

PRICE_RE = re.compile(r"Rs\.?\s?\d")
SINHALA_RE = re.compile(r"[඀-෿]")


def load_shop() -> FakeSupabase:
    snapshot = json.loads((HERE / "snapshot.json").read_text())
    business_id = settings.business_id
    fake = FakeSupabase()
    fake.seed("businesses", [{
        "id": business_id, "name": snapshot["business"]["name"],
        "wa_phone_number_id": "EVAL", "profile": snapshot["business"]["profile"],
    }])
    fake.seed("menu_items", [row | {"business_id": business_id} for row in snapshot["menu_items"]])
    fake.seed("faqs", [
        faq | {"id": str(uuid.uuid4()), "business_id": business_id} for faq in snapshot["faqs"]
    ])

    async def get_db() -> FakeSupabase:
        return fake

    for name in dir(db):
        module = getattr(db, name)
        if hasattr(module, "get_db") and module is not db:
            module.get_db = get_db
    db.business.clear_cache()
    return fake


def check(expect: dict[str, Any], reply: str, tools: list[str], answered_by: str) -> list[str]:
    """Every way this reply falls short of `expect`."""
    failures = []
    low = reply.lower()
    if "answered_by" in expect and expect["answered_by"] != answered_by:
        failures.append(f"answered by {answered_by}, expected {expect['answered_by']}")
    if expect.get("has_price") and not PRICE_RE.search(reply):
        failures.append("no price in the reply")
    for text in expect.get("contains", []):
        if text.lower() not in low:
            failures.append(f"missing {text!r}")
    if expect.get("contains_any") and not any(t.lower() in low for t in expect["contains_any"]):
        failures.append(f"none of {expect['contains_any']!r}")
    for text in expect.get("not_contains", []):
        if text.lower() in low:
            failures.append(f"says {text!r}")
    for tool in expect.get("tools", []):
        if tool not in tools:
            failures.append(f"did not call {tool}")
    for tool in expect.get("no_tools", []):
        if tool in tools:
            failures.append(f"called {tool}")
    script = expect.get("script")
    if script == "sinhala" and not SINHALA_RE.search(reply):
        failures.append("no Sinhala script in the reply")
    if script == "latin" and SINHALA_RE.search(reply):
        failures.append("Sinhala script in a reply to an English/Singlish customer")
    if "max_chars" in expect and len(reply) > expect["max_chars"]:
        failures.append(f"{len(reply)} characters, limit {expect['max_chars']}")
    return failures


async def say(contact_id: str, item: Any, n: int) -> str:
    """Save one inbound message the way the handler would; return its text."""
    business_id = settings.business_id
    wa_id = f"eval.{contact_id}.{n}"
    if isinstance(item, str):
        await db.messages.save(business_id=business_id, contact_id=contact_id, direction="in",
                               sender="customer", body=item, message_type="text",
                               wa_message_id=wa_id, status="delivered")
        return item
    if "document" in item:
        caption = item.get("caption") or ""
        row = await db.messages.save(business_id=business_id, contact_id=contact_id,
                                     direction="in", sender="customer", body=caption or None,
                                     message_type="document", wa_message_id=wa_id,
                                     status="delivered", image_analysis_status="pending",
                                     media_mime="application/pdf",
                                     media_filename=item.get("filename") or "file.pdf")
        await db.messages.complete_image_analysis(str(row["id"]), item["document"])
        return caption
    if "image" in item:
        caption = item.get("caption") or ""
        row = await db.messages.save(business_id=business_id, contact_id=contact_id,
                                     direction="in", sender="customer", body=caption or None,
                                     message_type="image", wa_message_id=wa_id,
                                     status="delivered", image_analysis_status="pending")
        await db.messages.complete_image_analysis(str(row["id"]), item["image"])
        return caption
    row = await db.messages.save(business_id=business_id, contact_id=contact_id, direction="in",
                                 sender="customer", body=None, message_type="audio",
                                 wa_message_id=wa_id, status="delivered",
                                 transcription_status="pending")
    await db.messages.complete_transcription(str(row["id"]), item["voice"])
    return item["voice"]


async def run_case(case: dict, index: int, fake: FakeSupabase, use_code: bool) -> dict:
    business_id = settings.business_id
    contact = await db.contacts.get_or_create(business_id, f"9470{index:07d}", name=f"Eval {index}")
    contact_id = str(contact["id"])
    turns_out, failures, cost, n = [], [], 0.0, 0

    for t, turn in enumerate(case["turns"]):
        texts = []
        for item in turn["say"]:
            n += 1
            texts.append(await say(contact_id, item, n))

        quick = None
        if use_code and all(isinstance(i, str) for i in turn["say"]):
            quick = await fast_reply(business_id, texts)
        if quick is not None:
            reply, tools, answered_by, usage = quick.text, [], "code", TokenUsage()
        else:
            result = await run_agent(business_id=business_id, contact=contact,
                                     incoming_text=texts[-1])
            reply, tools, answered_by = result.text, result.tools_called, "model"
            usage = result.usage or TokenUsage()
        cost += usage.cost_usd()
        n += 1
        await db.messages.save(business_id=business_id, contact_id=contact_id, direction="out",
                               sender="agent", body=reply, message_type="text",
                               wa_message_id=f"eval.{contact_id}.{n}", status="sent")

        turn_failures = check(turn.get("expect", {}), reply, tools, answered_by)
        failures += [f"turn {t + 1}: {f}" for f in turn_failures]
        turns_out.append({"say": turn["say"], "reply": reply, "tools": tools,
                          "answered_by": answered_by, "cost_usd": usage.cost_usd(),
                          "failures": turn_failures})

    end = case.get("end", {})
    orders = [o for o in fake.rows("orders") if str(o.get("contact_id")) == contact_id]
    if "orders" in end and len(orders) != end["orders"]:
        failures.append(f"end: {len(orders)} orders, expected {end['orders']}")
    if "order_total" in end and (not orders or float(orders[-1]["total"]) != end["order_total"]):
        got = orders[-1]["total"] if orders else "none"
        failures.append(f"end: order total {got}, expected {end['order_total']}")

    return {"id": case["id"], "passed": not failures, "failures": failures,
            "cost_usd": round(cost, 5), "turns": turns_out}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="e.g. gpt-5.6-luna (default: LLM_MODEL)")
    parser.add_argument("--only", action="append", default=[], help="run just this case id")
    parser.add_argument("--no-code", action="store_true",
                        help="send everything to the model, as before the code replies")
    parser.add_argument("--show", action="store_true", help="print every transcript")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    if args.model:
        settings.llm_model = args.model
    model = settings.model
    if model in PRICES:
        (settings.llm_price_input, settings.llm_price_cached_input,
         settings.llm_price_cache_write, settings.llm_price_output) = PRICES[model]

    cases = [c for c in CASES if not args.only or c["id"] in args.only]
    fake = load_shop()
    gate = asyncio.Semaphore(args.concurrency)
    started = time.monotonic()

    async def one(i: int, case: dict) -> dict:
        async with gate:
            try:
                return await run_case(case, i, fake, use_code=not args.no_code)
            except Exception as exc:  # a crash is a failure, not the end of the run
                return {"id": case["id"], "passed": False, "cost_usd": 0.0, "turns": [],
                        "failures": [f"crashed: {type(exc).__name__}: {exc}"]}

    results = await asyncio.gather(*(one(i, c) for i, c in enumerate(cases)))

    for result in results:
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark}  {result['id']:<42} ${result['cost_usd']:.4f}")
        for failure in result["failures"]:
            print(f"        - {failure}")
        if args.show or not result["passed"]:
            for turn in result["turns"]:
                said = " | ".join(s if isinstance(s, str) else f"[{next(iter(s))}]" for s in turn["say"])
                print(f"        C: {said}")
                print("        A: " + turn["reply"].replace("\n", "\n           ")[:900])
                print(f"           ({turn['answered_by']}, tools={turn['tools']})")

    passed = sum(r["passed"] for r in results)
    replies = sum(len(r["turns"]) for r in results)
    by_code = sum(t["answered_by"] == "code" for r in results for t in r["turns"])
    cost = sum(r["cost_usd"] for r in results)
    print(f"\n{model}: {passed}/{len(results)} cases passed · {replies} replies "
          f"({by_code} by code) · ${cost:.4f} · ${cost / max(replies, 1):.4f} per reply · "
          f"{time.monotonic() - started:.0f}s")

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{stamp}-{model}{'-nocode' if args.no_code else ''}.json"
    out.write_text(json.dumps({"model": model, "results": results}, ensure_ascii=False, indent=1))
    print(f"saved {out.relative_to(HERE.parent)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
