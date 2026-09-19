#!/usr/bin/env python3
"""Mint a device token for a POS terminal.

    python3 scripts/mint_device_token.py --device-id MAC1 --name "Shop Mac — counter"

The raw token is printed ONCE and never stored — only its sha256 goes in the
database. If it is lost, revoke the row and mint another; there is no recovery,
which is the point of storing a hash.

The device id is short and uppercase because it is printed into every bill
number that device issues (KF-MAC1-20260919-003). That prefix is what stops two
shop Macs both issuing -001 on the same day.

Staff can do the same thing from the dashboard via POST /devices; this exists so
the first token can be created before any dashboard UI for it is built.

Run it with the backend's virtualenv, from the repository root:
    backend/.venv/bin/python scripts/mint_device_token.py --device-id MAC1 --name "Shop Mac"
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

# The application lives in backend/; scripts are run from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import db  # noqa: E402
from config import settings  # noqa: E402

DEVICE_ID = re.compile(r"^[A-Z0-9]{2,6}$")


async def mint(device_id: str, name: str, created_by: str) -> int:
    existing = await db.devices.list_for_business(settings.business_id)
    clash = [d for d in existing if d.get("device_id") == device_id and not d.get("revoked_at")]
    if clash:
        print(
            f"error: device {device_id} already has a live token "
            f"({clash[0].get('token_prefix')}…). Revoke it before minting another.",
            file=sys.stderr,
        )
        return 1

    device, raw = await db.devices.create(
        business_id=settings.business_id,
        device_id=device_id,
        name=name,
        created_by=created_by,
    )

    print()
    print("  Device token created. This is the only time it will be shown.")
    print()
    print(f"    device    {device['device_id']} — {device['name']}")
    print(f"    token     {raw}")
    print()
    print("  Paste it into the POS under Settings -> Device token.")
    print("  Lost it? Revoke this device and mint another; it cannot be recovered.")
    print()
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mint a POS device token.",
        epilog="The token is shown once. Only its hash is stored.",
    )
    parser.add_argument(
        "--device-id",
        required=True,
        help="Short uppercase id, e.g. MAC1. Appears in every bill number this device issues.",
    )
    parser.add_argument("--name", required=True, help='Human label, e.g. "Shop Mac — counter"')
    parser.add_argument("--created-by", default="owner")
    args = parser.parse_args()

    device_id = args.device_id.strip().upper()
    if not DEVICE_ID.match(device_id):
        print(
            f"error: --device-id must be 2-6 characters of A-Z0-9, got {args.device_id!r}",
            file=sys.stderr,
        )
        return 2

    try:
        return await mint(device_id, args.name.strip(), args.created_by)
    finally:
        await db.close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
