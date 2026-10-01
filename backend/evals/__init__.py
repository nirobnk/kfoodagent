"""Replay real customer conversations against the agent and check what it says.

Run from backend/:
    .venv/bin/python -m evals.run                      # every case, the configured model
    .venv/bin/python -m evals.run --model gpt-5.6-luna # try another model
    .venv/bin/python -m evals.run --only price-list-kiyada
    .venv/bin/python -m evals.snapshot                 # refresh the catalogue copy

It calls the real model, so it costs money (about $1-2 a run on gpt-5.6-terra),
but it never touches Supabase or WhatsApp: the shop runs in memory from
snapshot.json.
"""
