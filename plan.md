# plan.md — WhatsApp AI Agent + CRM

> This file is the single source of truth for the build.
> Claude Code: read this file before every session. Work **one phase at a time**.
> Do not skip ahead. Do not start Phase N+1 until Phase N passes its "Done when" test.

---

## 1. What we are building

A WhatsApp AI agent for **K-Food (kfoods.lk)**, with a small CRM and an admin chat dashboard.

Three parts:

1. **Backend** — FastAPI. Receives WhatsApp messages, runs a LangGraph agent, sends replies.
2. **Database** — Supabase (Postgres). Stores contacts, messages, orders, notes.
3. **Dashboard** — Next.js. A WhatsApp-style chat UI for staff, with an agent/human toggle.

K-Food is the **pilot**. If it works, the same code becomes a SaaS for other Sri Lankan small businesses. So we build single-tenant now, but multi-tenant-ready (see §4).

---

## 2. Decisions already made — do not re-open these

| Topic | Decision | Why |
|---|---|---|
| WhatsApp access | **Standard Cloud API**, direct from Meta | Coexistence needs Tech Provider status or a paid BSP. Not available to a solo dev. |
| Phone number | Meta **test number** for Phases 0–6. A **new SIM** at go-live. | Standard Cloud API removes a number from the WhatsApp Business App. The current kfoods.lk number must stay on the app. |
| Database | **Supabase** | Postgres + Auth + Realtime + Storage in one. No separate commerce server. |
| Agent framework | **LangGraph** | Already familiar. Good tool-calling and state handling. |
| LLM | **OpenRouter** (configurable via env) — see §11 | Was "Gemini API direct". OpenRouter keeps one key and one bill across every model, and the provider already sat behind a single wrapper, so switching cost nothing. |
| Frontend | Next.js (App Router) + Tailwind | Same stack as the existing store. |

---

## 3. Tech stack

- Python 3.11+, FastAPI, Uvicorn
- LangGraph + LangChain
- `supabase-py` (backend), `@supabase/supabase-js` (frontend)
- Next.js 14+ App Router, TypeScript, Tailwind
- ngrok (local development only)
- Deployment: Railway or Fly.io (backend), Vercel (frontend)

---

## 4. Repository layout

```
/
├── plan.md                  <- this file
├── README.md
├── .env.example
├── backend/
│   ├── main.py              <- FastAPI app, webhook routes
│   ├── config.py            <- env vars, validated at startup
│   ├── whatsapp/
│   │   ├── client.py        <- send text, send template, mark read
│   │   ├── parser.py        <- turn Meta's JSON into a clean object
│   │   └── window.py        <- 24-hour window logic
│   ├── db/
│   │   ├── client.py        <- supabase client singleton
│   │   ├── contacts.py
│   │   ├── messages.py
│   │   ├── orders.py
│   │   └── notes.py
│   ├── agent/
│   │   ├── graph.py         <- LangGraph graph definition
│   │   ├── state.py         <- AgentState TypedDict
│   │   ├── prompts.py       <- system prompt
│   │   └── tools/
│   │       ├── menu.py
│   │       ├── orders.py
│   │       ├── notes.py
│   │       └── escalate.py
│   └── tests/
├── dashboard/               <- Next.js app
│   ├── app/
│   │   ├── page.tsx         <- chat list + thread
│   │   └── orders/page.tsx  <- order board
│   ├── components/
│   ├── lib/supabase.ts
│   └── ...
└── supabase/
    └── migrations/          <- numbered .sql files, never edited after applying
```

**Multi-tenant rule:** every table gets a `business_id uuid` column from day one. For now it always holds one fixed K-Food UUID. Never hardcode K-Food data inside queries. This makes SaaS later a config change, not a rewrite.

---

## 5. Database schema

Create as `supabase/migrations/0001_init.sql`.

```sql
create extension if not exists "pgcrypto";

create table businesses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  wa_phone_number_id text not null,
  created_at timestamptz default now()
);

create table contacts (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id),
  wa_id text not null,                       -- customer phone, e.g. 94771234567
  name text,
  language text default 'en',                -- en | si | ta
  tags text[] default '{}',
  human_takeover boolean default false,
  takeover_started_at timestamptz,
  last_customer_message_at timestamptz,      -- drives the 24-hour window
  first_seen timestamptz default now(),
  last_seen timestamptz default now(),
  unique (business_id, wa_id)
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id),
  contact_id uuid not null references contacts(id) on delete cascade,
  direction text not null check (direction in ('in','out')),
  sender text not null check (sender in ('customer','agent','human')),
  body text,
  media_url text,
  wa_message_id text unique,                 -- Meta's id. Used for idempotency.
  status text default 'sent',                -- sent | delivered | read | failed
  created_at timestamptz default now()
);

create table orders (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id),
  contact_id uuid not null references contacts(id),
  order_number serial,
  items jsonb not null default '[]',
  total numeric(10,2) default 0,
  status text default 'new'
    check (status in ('new','confirmed','preparing','dispatched','delivered','cancelled')),
  notes text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table notes (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id),
  contact_id uuid not null references contacts(id) on delete cascade,
  note text not null,
  created_by text default 'agent',
  created_at timestamptz default now()
);

create table menu_items (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id),
  name text not null,
  description text,
  price numeric(10,2) not null,
  category text,
  available boolean default true
);

create index on messages (contact_id, created_at desc);
create index on orders (business_id, status, created_at desc);
create index on contacts (business_id, last_seen desc);
```

> **Built version:** the applied schema is `supabase/migrations/0001_init.sql`. It follows the
> table list above and adds what the build turned out to need: a `business_members` table
> (Supabase Auth user → business, without which RLS has nothing to check), a `templates`
> table, and the columns `contacts.unread_count`, `contacts.takeover_by`,
> `messages.message_type`, `messages.template_name`, `messages.error`. RLS lives in
> `0002_rls.sql`, the atomic unread counter in `0003_functions.sql`.

**Security:** enable Row Level Security on every table before deployment. The backend uses the **service role key** (bypasses RLS, server-side only). The dashboard uses the **anon key** plus Supabase Auth, and RLS policies restrict rows to the signed-in user's `business_id`. This is Phase 6 work, but never ship without it.

---

## 6. Environment variables

`.env.example`:

```
# WhatsApp Cloud API
WA_ACCESS_TOKEN=
WA_PHONE_NUMBER_ID=
WA_BUSINESS_ACCOUNT_ID=
WA_VERIFY_TOKEN=            # any random string you invent
WA_API_VERSION=v26.0

# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=  # backend only, never in the frontend

# LLM
LLM_PROVIDER=gemini
GEMINI_API_KEY=
LLM_MODEL=gemini-2.0-flash

# App
BUSINESS_ID=
AUTO_RETURN_MINUTES=30
LOG_LEVEL=INFO
```

Frontend `.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

> **Built version:** `.env.example` also carries `WA_APP_SECRET` (webhook signature
> verification), `SUPABASE_ANON_KEY` and `SUPABASE_JWT_SECRET` (validating dashboard
> tokens), `ENVIRONMENT`, `CORS_ORIGINS`, `SEND_RATE_LIMIT_PER_MINUTE`, `REQUIRE_AUTH`,
> `HISTORY_TURNS`, `NOTES_LIMIT` and `LLM_MAX_TOOL_LOOPS`.

Never commit real `.env` files. `config.py` must fail loudly at startup if a required variable is missing.

---

## 7. Build phases

### Phase 0 — Setup

**Tasks**
- Create the repo, both folders, `.env.example`, `.gitignore`.
- Create a Supabase project. Run `0001_init.sql`. Insert one `businesses` row for K-Food. Copy its UUID into `BUSINESS_ID`.
- Create a Meta Developer account → new app → add the **WhatsApp** product.
- Copy the test number's `phone_number_id` and temporary access token.
- Add your own phone as a test recipient (up to 5 allowed).
- Install ngrok.

**Done when:** you can send yourself a test message from the Meta dashboard "Send message" button and receive it on your phone.

---

### Phase 1 — The pipe (echo bot, no AI)

Prove messages flow both ways before adding any intelligence.

**Tasks**
- `GET /webhook` — verify handshake. Compare `hub.verify_token` to `WA_VERIFY_TOKEN`. Return `hub.challenge` as **plain text**, not JSON.
- `POST /webhook` — return `200 OK` immediately, then process in a background task.
- `whatsapp/parser.py` — extract `wa_id`, `text.body`, `wa_message_id`, `timestamp` from Meta's nested JSON. Handle status-update payloads (delivered/read) that contain no message — ignore them quietly.
- `whatsapp/client.py` — `send_text(wa_id, body)` via `POST /{version}/{phone_number_id}/messages`.
- Echo back: "You said: {body}".

**Critical:** Meta retries the webhook if you are slow. Always return 200 within ~5 seconds, then do the real work asynchronously. Otherwise you get duplicate messages.

**Done when:** you message the test number from your phone and get the echo back within 3 seconds.

---

### Phase 2 — Database wiring

**Tasks**
- `db/contacts.py` — `get_or_create(wa_id)`, `touch(wa_id)` (updates `last_seen` and `last_customer_message_at`).
- `db/messages.py` — `save(...)`. **Idempotency:** if `wa_message_id` already exists, skip. Meta retries; without this you will store duplicates.
- Log every inbound and outbound message.
- Add `GET /health` returning DB connection status.

**Done when:** every message you send appears exactly once in the `messages` table, and a `contacts` row is created on first contact.

---

### Phase 3 — The LangGraph agent

**State** (`agent/state.py`):

```python
class AgentState(TypedDict):
    wa_id: str
    contact: dict          # name, language, tags
    messages: list         # last ~10 turns, loaded from DB
    recent_notes: list
    open_order: dict | None
    should_escalate: bool
```

**Graph shape:** `load_context → agent → tools → agent → ... → respond`

Use the standard LangGraph ReAct pattern: the `agent` node calls the LLM with tools bound; a conditional edge routes to `tools` if there is a tool call, otherwise to the end.

**Tools**
- `search_menu(query)` → reads `menu_items`
- `create_order(items)` → writes `orders`, returns `order_number`
- `check_order_status()` → latest order for this contact
- `save_note(note)` → writes `notes` ("no spicy", "orders every Friday")
- `escalate_to_human(reason)` → sets `human_takeover = true`

**System prompt rules** (`agent/prompts.py`):
- You are the K-Food assistant. Friendly, short, never invent menu items or prices.
- Always call `search_menu` before quoting any price.
- Reply in the customer's language (English, Sinhala, or Singlish — match what they used).
- **Answer in ONE message.** Do not split across several sends. Each message costs money.
- Never promise a delivery time. Say staff will confirm.
- Call `escalate_to_human` for: complaints, refunds, anything about a wrong or missing order, or when unsure.

**Context loading:** pass only the last ~10 messages plus up to 5 notes. Do not send the entire history — it is slow and expensive.

**Done when:** you can ask "what ramen do you have?", get real prices from the database, place an order, and see the row in `orders`.

---

### Phase 4 — Orders and status updates

**Tasks**
- `PATCH /orders/{id}/status` — updates status, then sends a WhatsApp notification.
- Message per status:
  - `confirmed` → "Order #1043 confirmed. Total Rs. 2,400."
  - `preparing` → "We are preparing order #1043."
  - `dispatched` → "Order #1043 is on the way."
  - `delivered` → "Order #1043 delivered. Thank you!"
- Route through `window.py`: inside 24 hours send free text, outside send the matching template (Phase 6).

**Done when:** changing a status via the API sends the right WhatsApp message to the customer.

---

### Phase 5 — Next.js dashboard

**Layout** — copy WhatsApp Web, because staff already understand it.

- **Left:** chat list, newest first, unread count, and an icon showing who is handling it (robot = agent, person = human).
- **Right:** the thread, with a toggle and a window badge in the header.

**Realtime:** subscribe to `messages` inserts with Supabase Realtime, filtered by `contact_id`. No polling.

```ts
supabase
  .channel(`chat:${contactId}`)
  .on('postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'messages',
      filter: `contact_id=eq.${contactId}` },
    (payload) => appendMessage(payload.new))
  .subscribe();
```

**The agent/human switch** — this is one `if` in the webhook, before the agent runs:

```python
contact = contacts.get_or_create(wa_id)
messages.save(contact, "in", "customer", body, wa_message_id)

if contact["human_takeover"]:
    return               # agent stays silent; staff see it in the dashboard
run_agent(contact, body)
```

**Auto-return:** a background job every 5 minutes sets `human_takeover = false` where `takeover_started_at` is older than `AUTO_RETURN_MINUTES`. Without this, staff forget to switch back and customers get silence.

**Sending from the UI:** the dashboard calls `POST /messages/send` on the backend. The frontend never holds the WhatsApp token.

**Orders board:** `/orders` — today's orders as cards, with status buttons. This may also live as a tab inside the existing K-Food POS app if that is faster.

**Done when:** two browser tabs stay in sync live, the toggle stops and starts the agent, and staff can reply by hand.

---

### Phase 6 — 24-hour window, templates, security

**Window logic** (`whatsapp/window.py`):

```python
def can_send_free_text(contact) -> bool:
    last = contact.get("last_customer_message_at")
    if not last:
        return False
    return (now_utc() - last) < timedelta(hours=24)
```

- Call this before **every** outbound send. If it returns `False`, send an approved template instead.
- Show a countdown badge in the dashboard header: "Free reply: 4h 12m left".
- When it reaches zero, disable the text box and show template buttons.

**Templates to submit for Meta approval** (category: Utility):
- `order_confirmed` — "Hello {{1}}, your K-Food order #{{2}} is confirmed. Total Rs. {{3}}."
- `order_dispatched` — "Hello {{1}}, your K-Food order #{{2}} is on the way."
- `order_delivered` — "Order #{{1}} delivered. Thank you for choosing K-Food!"

Store approved template names in a `templates` table with their variable order, so the code does not hardcode them.

**Cost note:** from 1 October 2026 Meta charges for service messages and utility templates sent inside the 24-hour window, with the first 1,000 service messages per number per month free. This is why the prompt says one message per reply. Track monthly message count in the dashboard.

**Security checklist before deploy:**
- [ ] RLS enabled on all tables, with policies scoped to `business_id`
- [ ] Service role key exists only in backend env, never in `NEXT_PUBLIC_*`
- [ ] Webhook verifies Meta's `X-Hub-Signature-256` header against the app secret
- [ ] Dashboard behind Supabase Auth
- [ ] Rate limit `POST /messages/send`

---

### Phase 7 — Go live

**Tasks**
- Buy a new SIM for the agent. Do **not** use the current kfoods.lk app number.
- Add it as a real phone number in the Meta app. Verify it.
- Complete Meta Business Verification (needed to raise the messaging limit).
- Generate a permanent System User token. The temporary one expires in 24 hours.
- Deploy the backend to Railway or Fly.io. Point the Meta webhook at the production URL.
- Deploy the dashboard to Vercel.
- Seed the real menu into `menu_items`.
- Put the new number on the website, Google profile, and Facebook page.

**Done when:** a real customer messages the new number and completes an order end to end.

---

## 8. Rules for Claude Code

- Work **one phase at a time**. Stop and report at each "Done when".
- Write the test first when the behaviour is checkable (parser, window logic, idempotency).
- Never hardcode secrets. Read everything from `config.py`.
- Never hardcode `business_id` inside a query — pass it in.
- Keep the WhatsApp API surface inside `whatsapp/client.py`. No `requests.post` to Meta anywhere else.
- Keep all database access inside `db/`. No raw Supabase calls in `main.py` or in agent tools.
- Log every outbound send with `wa_id`, template-or-text, and the result.
- Small commits, conventional messages: `feat(webhook): handle status payloads`.
- If something in this plan turns out to be wrong, **update plan.md in the same commit**.

---

## 9. Known risks

| Risk | Handling |
|---|---|
| Duplicate messages from Meta retries | Unique `wa_message_id` + return 200 fast |
| Agent hallucinates prices | Tool-only pricing; prompt forbids guessing |
| Agent and human reply at once | `human_takeover` flag checked before the agent runs |
| Staff forget to switch back to agent | Auto-return job after 30 minutes |
| Sends fail silently outside 24 hours | Window check before every send; dashboard badge |
| Token expires | Permanent System User token before go-live |
| Costs grow with volume | One message per reply; monthly counter in dashboard |

---

## 10. Out of scope for v1

Payment links, delivery tracking, voice notes, multi-language templates, other businesses (SaaS), analytics dashboard. Revisit after the K-Food pilot runs for one month.

---

## 11. Build log — what the implementation changed

Phases 1–6 are implemented and tested (`backend/tests`, 89 tests, no network). Phase 0 and
Phase 7 are account and hardware steps that stay manual; the checklist for them is in
`README.md`.

Corrections and additions the build forced, per the rule in §8:

| Area | What changed | Why |
|---|---|---|
| Schema | Added `business_members` | RLS policies need a user → business mapping; §5 had none, so the dashboard could not be secured |
| Schema | Added `templates`, `contacts.unread_count`, `contacts.takeover_by`, `messages.message_type`, `messages.template_name`, `messages.error` | Needed by the window/template logic and the inbox UI |
| Schema | `bump_unread()` SQL function | An unread counter incremented from the application loses counts under webhook retries |
| Agent | LangGraph node signatures must annotate `config: RunnableConfig` | LangGraph 1.0 only injects the config when it is typed; with `Any` the node fails at runtime |
| Agent | Tools read their business/contact from the run config, not from closures | One compiled graph is reused across requests |
| Agent | An LLM failure escalates to a human and sends the fallback line | Nobody may be left with silence |
| Inbound | Media with no caption (photo, voice note, document) escalates to a human | The agent cannot read it; stickers are ignored quietly |
| Outbound | One module (`outbound.py`) owns the window check, the template fallback and the message log | §6 says "call this before every outbound send" — one door makes that checkable |
| Staff API | `POST /messages/send` turns on `human_takeover` by default | Otherwise a staff reply and an agent reply can cross, which is a listed risk in §9 |
| Security | Webhook signature check, Supabase-token auth with membership check, rate limit, production startup refuses unresolved warnings | §6 checklist, enforced in code rather than by memory |
| Ops | One backend instance only | The auto-return job and the per-contact locks are in-process |

### Catalogue import (added after the first build)

The plan assumed a restaurant menu — dishes with one price each. The real kfoods.lk
business is an **online Korean grocery store**: 30 products, each sold as a single, a
5 Pack and a carton of 20, couriered island-wide, paid by bank transfer. The build was
changed to match, using the site's own export as the source of truth.

| Area | What changed |
|---|---|
| Source data | `data/kfood-catalog.json` + `data/kfood-images.json`, exported from `static/kfood`. 20 real product photos copied into `assets/products/`; 10 products show a placeholder on the site and are recorded as having no photo |
| Schema | `0004_catalog.sql`: `menu_items` gains sku, handle, variant, units, brand, Korean name, pack size, heat level, allergens, ingredients, nutrition, images; `businesses.profile jsonb` holds delivery/payment/returns/contact; new `faqs` table; `orders` gains `subtotal` and `delivery_fee` |
| Seeding | `scripts/build_seed.py` generates `supabase/seed_catalog.sql` (90 variants, profile, 9 FAQs). Re-run it when the website changes — never hand-edit the SQL |
| Tools | `search_menu` now returns every variant with its SKU; new `product_details` (allergens, nutrition, cooking) and `store_info` (delivery, payment, returns, contact, how to order); `create_order` takes SKUs and adds the Rs. 400 delivery fee, waived over Rs. 5,000 |
| Search | Synonym expansion: customers type "ramen", the packs are spelled "ramyun". Against the real data that is the difference between 3 and 16 matching products |
| Prompt | Rewritten for an online store: three pack sizes, bank transfer only, no card payment, no walk-in shop, never promise a delivery date, allergy questions quote the pack exactly |
| Dashboard | New `/products` catalogue page with photos, every pack price and allergens; order cards show items + delivery separately |

Verified by applying all four migrations and both seed files to a local Postgres 17
database: 90 menu_items across 30 products, 9 FAQs, profile intact, and the seed is
idempotent when re-run.

### LLM provider

Changed from Gemini-direct to **OpenRouter**, which speaks the OpenAI API — so
`langchain-openai` now serves both it and OpenAI, and `agent/llm.py` gained an
`openrouter` branch with the attribution headers. `LLM_MODEL` becomes a routed id
(`google/gemini-3.1-flash-lite` by default).

The one hard requirement is **tool calling**: every price, order, delivery rule and
allergen line comes from a tool, so a model without it has nothing truthful to say.
Checked against OpenRouter's live catalogue — 375 of 444 models support tools, and
`google/gemini-2.0-flash-001`, which the plan would have suggested, no longer exists there.

### Graph API version

The plan was written against `v21.0`. Meta's current version is **v26.0**, so that is the
default in `config.py` and in `.env.example`. It stays an environment variable: bumping a
Graph API version is a config change, never a code change.

### Supabase keys (September 2026)

Supabase replaced the legacy JWT keys with `sb_secret_…` / `sb_publishable_…`, and
publishes signing keys at `/auth/v1/.well-known/jwks.json`. The build now:

* reads `SUPABASE_SECRET_KEY` / `SUPABASE_PUBLISHABLE_KEY`, falling back to
  `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` so either generation works;
* verifies staff tokens locally against JWKS (ES256) when `SUPABASE_JWKS_URL` is set,
  then HS256, then a call to `/auth/v1/user` — in that order;
* trims `/rest/v1` and friends off `SUPABASE_URL`, because pasting the REST URL from the
  dashboard makes every query 404;
* keeps one env file at the repository root, resolved by absolute path. Inline
  `# comments` after a value are not stripped by python-dotenv and become part of the
  value, so the example file keeps comments on their own lines.

### Still open before go-live

* Meta Business Verification, permanent System User token, the new SIM (§7).
* Templates must be approved by Meta, then flipped to `approved = true` in `templates`.
* Real photos for the 10 products that still show "photo coming soon" on kfoods.lk.
* Confirm with the shop that the exported prices are current before go-live.
