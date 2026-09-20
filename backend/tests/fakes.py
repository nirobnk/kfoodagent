"""An in-memory stand-in for the Supabase client.

It implements only the query surface this codebase actually uses, plus the one
database behaviour the application depends on for correctness: the unique index
on messages.wa_message_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class UniqueViolation(Exception):
    pass


@dataclass
class Response:
    data: list[dict[str, Any]]
    count: int | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches_ilike(value: Any, pattern: str) -> bool:
    if value is None:
        return False
    text = str(value).lower()
    needle = pattern.lower().strip("%")
    if pattern.startswith("%") and pattern.endswith("%"):
        return needle in text
    return text == needle


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table_name = table
        self.mode = "select"
        self.payload: Any = None
        self.patch: dict[str, Any] = {}
        self.filters: list[tuple[str, str, Any]] = []
        self.or_clause: str | None = None
        self._limit: int | None = None
        self.order_by: list[tuple[str, bool]] = []
        self.count_mode: str | None = None
        self.on_conflict: str | None = None
        self.ignore_duplicates = False

    # -- builders ----------------------------------------------------------
    def select(self, *args: Any, **kwargs: Any) -> "FakeQuery":
        if self.mode == "select":
            self.count_mode = kwargs.get("count")
        return self

    def insert(self, payload: Any) -> "FakeQuery":
        self.mode = "insert"
        self.payload = payload
        return self

    def update(self, patch: dict[str, Any]) -> "FakeQuery":
        self.mode = "update"
        self.patch = patch
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None,
               ignore_duplicates: bool = False, **_: Any) -> "FakeQuery":
        self.mode = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        self.ignore_duplicates = ignore_duplicates
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, "eq", value))
        return self

    def lt(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, "lt", value))
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, "gte", value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.filters.append((column, "in", values))
        return self

    def ilike(self, column: str, pattern: str) -> "FakeQuery":
        self.filters.append((column, "ilike", pattern))
        return self

    def or_(self, clause: str) -> "FakeQuery":
        self.or_clause = clause
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_by.append((column, desc))
        return self

    def limit(self, value: int) -> "FakeQuery":
        self._limit = value
        return self

    # -- execution ---------------------------------------------------------
    async def execute(self) -> Response:
        rows = self.db.tables.setdefault(self.table_name, [])

        if self.mode == "insert":
            return Response(self._insert(rows))
        if self.mode == "upsert":
            return Response(self._upsert(rows))

        selected = [row for row in rows if self._passes(row)]

        if self.mode == "update":
            for row in selected:
                row.update(self.patch)
                if "updated_at" in row:
                    row["updated_at"] = _now()
            return Response([dict(row) for row in selected])

        for column, desc in reversed(self.order_by):
            selected.sort(key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)

        total = len(selected)
        if self._limit is not None:
            selected = selected[: self._limit]
        return Response([dict(row) for row in selected], count=total)

    # -- internals ---------------------------------------------------------
    def _insert(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payloads = self.payload if isinstance(self.payload, list) else [self.payload]
        created = []
        for payload in payloads:
            row = self.db.new_row(self.table_name, payload)
            self.db.enforce_unique(self.table_name, row)
            rows.append(row)
            if self.table_name == "inventory_movements":
                self.db.apply_stock_trigger(row)
            created.append(dict(row))
        return created

    def _upsert(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payloads = self.payload if isinstance(self.payload, list) else [self.payload]
        created = []
        for payload in payloads:
            key = self.on_conflict
            conflicting = None
            if key and payload.get(key) is not None:
                conflicting = next((r for r in rows if r.get(key) == payload[key]), None)
            if conflicting is not None:
                if self.ignore_duplicates:
                    continue  # postgrest returns no row for a skipped upsert
                conflicting.update(payload)
                created.append(dict(conflicting))
                continue
            row = self.db.new_row(self.table_name, payload)
            rows.append(row)
            created.append(dict(row))
        return created

    def _passes(self, row: dict[str, Any]) -> bool:
        for column, op, value in self.filters:
            actual = row.get(column)
            if op == "eq" and actual != value:
                return False
            if op == "in" and actual not in value:
                return False
            if op == "ilike" and not _matches_ilike(actual, value):
                return False
            if op == "lt":
                if actual is None or str(actual) >= str(value):
                    return False
            if op == "gte":
                if actual is None or str(actual) < str(value):
                    return False

        if self.or_clause:
            for part in self.or_clause.split(","):
                column, _, pattern = part.partition(".ilike.")
                if pattern and _matches_ilike(row.get(column), pattern):
                    break
            else:
                return False
        return True


class FakeRpc:
    def __init__(self, db: "FakeSupabase", name: str, params: dict[str, Any]) -> None:
        self.db = db
        self.name = name
        self.params = params

    async def execute(self) -> Response:
        self.db.rpc_calls.append((self.name, self.params))
        if self.name == "bump_unread":
            for row in self.db.tables.get("contacts", []):
                if row["id"] == self.params.get("p_contact_id"):
                    row["unread_count"] = (row.get("unread_count") or 0) + 1
                    return Response([{"bump_unread": row["unread_count"]}])
        return Response([])


class FakeStorageBucket:
    def __init__(self, storage: "FakeStorage", bucket: str) -> None:
        self.storage = storage
        self.bucket = bucket

    async def upload(
        self, *, path: str, file: bytes, file_options: dict[str, Any]
    ) -> dict[str, str]:
        if self.storage.fail_with:
            raise self.storage.fail_with
        self.storage.files[(self.bucket, path)] = {
            "content": file,
            "options": dict(file_options),
        }
        return {"path": path}

    async def create_signed_url(self, path: str, expires_in: int) -> dict[str, str]:
        if (self.bucket, path) not in self.storage.files:
            raise RuntimeError("stored object not found")
        return {
            "signedUrl": f"https://storage.example/{self.bucket}/{path}?expires={expires_in}"
        }


@dataclass
class FakeStorage:
    files: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    fail_with: Exception | None = None

    def from_(self, bucket: str) -> FakeStorageBucket:
        return FakeStorageBucket(self, bucket)


@dataclass
class FakeSupabase:
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    rpc_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    storage: FakeStorage = field(default_factory=FakeStorage)
    _serial: int = 1000

    DEFAULTS: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "contacts": {
                "name": None,
                "language": "en",
                "tags": [],
                "human_takeover": False,
                "takeover_started_at": None,
                "takeover_by": None,
                "last_customer_message_at": None,
                "unread_count": 0,
            },
            "messages": {
                "body": None,
                "media_url": None,
                "message_type": "text",
                "template_name": None,
                "wa_message_id": None,
                "status": "sent",
                "error": None,
                "transcript": None,
                "transcription_status": None,
                "transcription_error": None,
            },
            "payment_receipts": {
                "order_id": None,
                "message_id": None,
                "whatsapp_media_id": None,
                "media_mime_type": None,
                "private_media_path": None,
                "file_sha256": None,
                "file_size_bytes": None,
                "storage_status": "not_applicable",
                "storage_error": None,
                "stored_at": None,
                "reported_detail": None,
                "extracted_data": {},
                "amount": None,
                "bank_name": None,
                "transaction_reference": None,
                "analysis_confidence": None,
                "review_status": "pending_review",
                "reviewed_by": None,
                "reviewed_at": None,
            },
            "orders": {
                "status": "new",
                "items": [],
                "total": 0,
                "subtotal": 0,
                "delivery_fee": 0,
                "discount": 0,
                "discount_note": None,
                "notes": None,
                "source": "agent",
                "external_ref": None,
            },
            "inventory_movements": {
                "order_id": None,
                "note": None,
                "created_by": "system",
            },
            "device_tokens": {
                "scopes": ["catalog", "orders"],
                "revoked_at": None,
                "revoked_by": None,
                "last_seen_at": None,
                "created_by": "owner",
            },
            "crm_tasks": {
                "contact_id": None,
                "order_id": None,
                "detail": None,
                "due_at": None,
                "priority": "normal",
                "done_at": None,
                "done_by": None,
                "assigned_to": None,
                "created_by": "staff",
            },
            "notes": {
                "created_by": "agent",
                "pinned": False,
            },
            "order_invoices": {
                "mismatch": False,
                "mismatch_detail": [],
                "lines": [],
                "payment_method": None,
                "catalog_version": None,
                "reviewed_at": None,
                "reviewed_by": None,
            },
        }
    )

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)

    def new_row(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {"id": str(uuid.uuid4())}
        row.update(self.DEFAULTS.get(table, {}))
        row.update({k: v for k, v in payload.items() if v is not None or k in row})
        row.setdefault("created_at", _now())
        if table == "orders":
            self._serial += 1
            row["order_number"] = self._serial
            row["updated_at"] = _now()
        if table == "crm_tasks":
            # 0008 puts the same set_updated_at trigger on this table.
            row["updated_at"] = _now()
        if table in ("contacts",):
            row.setdefault("first_seen", _now())
            row.setdefault("last_seen", _now())
        return row

    def enforce_unique(self, table: str, row: dict[str, Any]) -> None:
        if table == "messages" and row.get("wa_message_id"):
            existing = [
                r
                for r in self.tables.get("messages", [])
                if r is not row and r.get("wa_message_id") == row["wa_message_id"]
            ]
            if existing:
                raise UniqueViolation("duplicate key value violates unique constraint")
        if table == "inventory_movements" and row.get("reason") == "sold" and row.get("order_id"):
            existing = [
                r
                for r in self.tables.get("inventory_movements", [])
                if r is not row
                and r.get("reason") == "sold"
                and r.get("order_id") == row.get("order_id")
                and r.get("menu_item_id") == row.get("menu_item_id")
            ]
            if existing:
                raise UniqueViolation("one sale per order per item")
        if table == "contacts":
            existing = [
                r
                for r in self.tables.get("contacts", [])
                if r is not row
                and r.get("business_id") == row.get("business_id")
                and r.get("wa_id") == row.get("wa_id")
            ]
            if existing:
                raise UniqueViolation("duplicate contact")
        # order_invoices (business_id, bill_no) — the POS idempotency anchor.
        # Without this the replay test would exercise only the Python pre-check
        # and never the constraint that actually protects production.
        if table == "order_invoices" and row.get("bill_no"):
            existing = [
                r
                for r in self.tables.get("order_invoices", [])
                if r is not row
                and r.get("business_id") == row.get("business_id")
                and r.get("bill_no") == row.get("bill_no")
            ]
            if existing:
                raise UniqueViolation("duplicate bill number")
        # orders (business_id, external_ref) where external_ref is not null.
        if table == "orders" and row.get("external_ref"):
            existing = [
                r
                for r in self.tables.get("orders", [])
                if r is not row
                and r.get("business_id") == row.get("business_id")
                and r.get("external_ref") == row.get("external_ref")
            ]
            if existing:
                raise UniqueViolation("duplicate order external_ref")
        if table == "device_tokens" and row.get("token_hash"):
            existing = [
                r
                for r in self.tables.get("device_tokens", [])
                if r is not row and r.get("token_hash") == row.get("token_hash")
            ]
            if existing:
                raise UniqueViolation("duplicate device token hash")
        if table == "payment_receipts" and row.get("message_id"):
            existing = [
                r
                for r in self.tables.get("payment_receipts", [])
                if r is not row and r.get("message_id") == row.get("message_id")
            ]
            if existing:
                raise UniqueViolation("one receipt record per message")

    def apply_stock_trigger(self, row: dict[str, Any], *, removing: bool = False) -> None:
        """Stand in for inventory_movements_apply in 0005_inventory.sql.

        Without it the cached quantity never moves here, and every test about
        selling or restocking would pass against a number that production
        maintains and this fake does not.
        """
        delta = int(row.get("delta") or 0)
        if removing:
            delta = -delta
        for item in self.tables.get("menu_items", []):
            if item.get("id") == row.get("menu_item_id"):
                item["stock_quantity"] = int(item.get("stock_quantity") or 0) + delta

    # -- helpers for tests -------------------------------------------------
    def seed(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.tables.setdefault(table, []).extend(rows)

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.get(table, [])


class FakeWhatsApp:
    """Records what would have been sent to Meta."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.texts: list[tuple[str, str]] = []
        self.templates: list[tuple[str, str, list[Any]]] = []
        self.images: list[tuple[str, str, str]] = []
        self.read_receipts: list[str] = []
        self.media_downloads: dict[str, Any] = {}
        self.downloaded_media_ids: list[str] = []
        self.fail_with = fail_with
        self._counter = 0

    async def send_text(self, wa_id: str, body: str, **_: Any) -> str:
        if self.fail_with:
            raise self.fail_with
        self.texts.append((wa_id, body))
        self._counter += 1
        return f"wamid.OUT{self._counter}"

    async def send_image(self, wa_id: str, image_url: str, *, caption: str = "") -> str:
        if self.fail_with:
            raise self.fail_with
        self.images.append((wa_id, image_url, caption))
        self._counter += 1
        return f"wamid.IMG{self._counter}"

    async def send_template(self, wa_id: str, name: str, *, language: str = "en",
                            variables: Any = ()) -> str:
        if self.fail_with:
            raise self.fail_with
        self.templates.append((wa_id, name, list(variables)))
        self._counter += 1
        return f"wamid.TPL{self._counter}"

    async def mark_read(self, wa_message_id: str) -> None:
        self.read_receipts.append(wa_message_id)

    async def download_media(self, media_id: str, *, max_bytes: int) -> Any:
        self.downloaded_media_ids.append(media_id)
        media = self.media_downloads.get(media_id)
        if media is None:
            raise RuntimeError(f"no fake media configured for {media_id}")
        if len(media.content) > max_bytes:
            raise RuntimeError("fake media exceeds size limit")
        return media

    async def aclose(self) -> None:
        return None


# ---------------------------------------------------------------------------
# A small but real slice of the kfoods.lk catalogue, for tests that need one.
# Values are copied from data/kfood-catalog.json, so they match production.
# ---------------------------------------------------------------------------

KFOOD_PROFILE: dict[str, Any] = {
    "trading_name": "K FOOD",
    "website": "https://kfoods.lk/",
    "currency": "LKR",
    "brands": ["Binggrae", "Dong-A", "Migawon", "Nongshim", "OKF"],
    "categories": ["Instant Noodles", "Cup Noodles", "Beverages"],
    "area_served": "Sri Lanka (all 25 districts)",
    "contact": {
        "whatsapp": {"number": "94772953107", "displayNumber": "077 295 3107"},
        "email": {"address": "kfoodslk@gmail.com"},
        "social": {"facebook": "https://web.facebook.com/kfoodslk"},
    },
    "payment": {
        "methods": ["Bank Transfer"],
        "cardPaymentAvailable": False,
        "bankDetails": {
            "bank": "Hatton National Bank (HNB)",
            "branch": "Alawwa",
            "accountName": "Kumarasinghe H G B N",
            "accountNumber": "123020163895",
        },
        "process": "K FOOD confirms stock and total, the customer pays by bank transfer and "
        "sends the receipt on WhatsApp, then the order is dispatched.",
    },
    "delivery": {
        "coverage": "All 25 districts of Sri Lanka, island-wide",
        "fee": 400,
        "freeDeliveryThreshold": 5000,
        "estimatedTime": "2-4 days",
        "minimumOrder": "None — orders can be a single item up to a full carton",
    },
    "returns": {
        "window": "7 days from delivery",
        "process": "Message K FOOD on WhatsApp within 7 days of delivery.",
        "conditions": "Opened food packs cannot be returned, for food-safety reasons.",
    },
    "how_to_order": [
        {"step": 1, "title": "Fill your cart", "text": "Pick singles, 5 Packs or cartons."},
        {"step": 2, "title": "Add your address", "text": "Anywhere in Sri Lanka."},
    ],
}

_PRODUCTS = [
    {
        "handle": "shin-ramyun",
        "product_name": "Shin Ramyun Original",
        "brand": "Nongshim",
        "korean_name": "신라면",
        "category": "Instant Noodles",
        "pack_size": "120g",
        "heat_level": 4,
        "cook_time": "4-5 mins",
        "badge": "Best Seller",
        "short_description": "The beef-and-mushroom broth that made Korean instant noodles famous.",
        "ingredients": "Wheat flour, palm oil, red chilli pepper, beef bone extract.",
        "allergens": "Contains wheat, soy and beef. May contain milk, egg and fish.",
        "prefix": "RAM-SHIN",
        "prices": [("Single Pack", 1, 650), ("5 Pack", 5, 3250), ("Carton (20)", 20, 13000)],
        "photo": "assets/products/shin-ramyun.webp",
    },
    {
        "handle": "hotdak-original",
        "product_name": "Hot Dak Stir Fry Ramen Original",
        "brand": "Migawon",
        "korean_name": "핫닭",
        "category": "Instant Noodles",
        "pack_size": "140g",
        "heat_level": 5,
        "cook_time": "5 mins",
        "badge": None,
        "short_description": "Fire noodles with a sweet heat that keeps climbing.",
        "ingredients": "Wheat flour, palm oil, hot chicken sauce, chicken extract.",
        "allergens": "Contains wheat, soy, sesame and chicken. May contain milk, egg and fish.",
        "prefix": "RAM-HOTDAK",
        "prices": [("Single Pack", 1, 750), ("5 Pack", 5, 3750), ("Carton (20)", 20, 15000)],
        "photo": "assets/products/hotdak-original.jpeg",
    },
    {
        "handle": "banana-milk",
        "product_name": "Binggrae Banana Flavoured Milk",
        "brand": "Binggrae",
        "korean_name": "바나나맛 우유",
        "category": "Beverages",
        "pack_size": "200ml",
        "heat_level": None,
        "cook_time": None,
        "badge": "Popular",
        "short_description": "The banana milk in the round carton, chilled.",
        "ingredients": "Milk, water, sugar, skim milk powder and banana juice concentrate.",
        "allergens": "Contains milk.",
        "prefix": "DRK-BANANA",
        "prices": [("Single Carton", 1, 590), ("5 Pack", 5, 2950), ("Carton (20)", 20, 11800)],
        "photo": "assets/products/banana-milk.jpeg",
    },
]

KFOOD_FAQS = [
    {
        "question": "Where does K FOOD deliver?",
        "answer": "Everywhere in Sri Lanka. Courier is a flat LKR 400 island-wide and free on "
        "orders over LKR 5,000. Most orders arrive in 2-4 days.",
    },
    {
        "question": "How do I pay?",
        "answer": "Bank transfer to Hatton National Bank (HNB), Alawwa branch. There is no "
        "online card payment.",
    },
]


def seed_kfood(fake: "FakeSupabase", business_id: str) -> None:
    """Load the business profile, three products (nine variants) and two FAQs."""
    fake.seed(
        "businesses",
        [{"id": business_id, "name": "K FOOD", "wa_phone_number_id": "PNID",
          "profile": KFOOD_PROFILE}],
    )

    order = 0
    rows: list[dict[str, Any]] = []
    for product in _PRODUCTS:
        for label, units, price in product["prices"]:
            order += 1
            suffix = {1: "1", 5: "5", 20: "20"}[units]
            rows.append(
                {
                    "id": f"{product['handle']}-{units}",
                    "business_id": business_id,
                    "sku": f"{product['prefix']}-{suffix}",
                    "handle": product["handle"],
                    "name": f"{product['product_name']} — {label}",
                    "product_name": product["product_name"],
                    "variant_label": label,
                    "units": units,
                    "price": price,
                    "unit_price": product["prices"][0][2],
                    "brand": product["brand"],
                    "korean_name": product["korean_name"],
                    "category": product["category"],
                    "pack_size": product["pack_size"],
                    "heat_level": product["heat_level"],
                    "cook_time": product["cook_time"],
                    "badge": product["badge"],
                    "short_description": product["short_description"],
                    "long_description": product["short_description"],
                    "serving_suggestion": "Boil 550ml of water and cook for 4 to 5 minutes.",
                    "ingredients": product["ingredients"],
                    "allergens": product["allergens"],
                    "nutrition": {"basis": f"Per {product['pack_size']}", "energy": "520 kcal"},
                    "image_url": f"https://kfoods.lk/{product['handle']}.jpeg",
                    "image_file": product["photo"],
                    "product_url": f"https://kfoods.lk/products/{product['handle']}.html",
                    "sort_order": order,
                    "available": True,
                }
            )
    fake.seed("menu_items", rows)

    fake.seed(
        "faqs",
        [
            {"id": f"faq{index}", "business_id": business_id, "sort_order": index, **faq}
            for index, faq in enumerate(KFOOD_FAQS, start=1)
        ],
    )
