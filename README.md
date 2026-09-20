# K FOOD WhatsApp Agent + CRM

A WhatsApp AI agent for **K FOOD (kfoods.lk)** — an online Korean food store delivering
island-wide in Sri Lanka — with a small CRM and a WhatsApp-style staff dashboard.

* **Backend** — FastAPI. Receives WhatsApp webhooks, runs a LangGraph agent, sends replies.
* **Database** — Supabase (Postgres). Contacts, messages, orders, notes, menu, templates.
* **Dashboard** — Next.js. Live chat inbox with an agent/human toggle, an order board and the
  catalogue as staff see it.
* **Catalogue** — the real kfoods.lk products: 30 products × 3 pack sizes (single / 5 Pack /
  carton of 20) = 90 SKUs, with prices, heat levels, allergens, nutrition and photos.

Single-tenant for the K-Food pilot, multi-tenant-ready: every table carries `business_id`
and no query hardcodes it.

---

## How a message flows

```
customer → WhatsApp → Meta Cloud API
                          │  POST /webhook  (signature checked, 200 in ms)
                          ▼
                    background task
                          │
   1. seen this wa_message_id before?  → stop (Meta retries; we must not answer twice)
   2. contacts.get_or_create
   3. messages.save            (inbound row)
   4. contacts.touch_inbound   (opens the 24-hour window)
   5. human_takeover on?       → stop (staff are handling it; the agent stays silent)
   6. LangGraph agent          load_context → agent ⇄ tools → reply
   7. outbound.send_text       (window checked once, here) → messages.save (outbound row)
                          │
                          ▼
              Supabase Realtime → dashboard updates live
```

Everything the agent knows about prices comes from `menu_items` through the `search_menu`
tool. Order totals — including the Rs. 400 island-wide delivery fee, waived over Rs. 5,000 —
are recomputed from the database inside `create_order`, so a hallucinated price can never
reach a customer. Delivery, payment, returns and contact answers come from the business
profile through `store_info`, not from the model's memory. The bank details go out through
`payment_details`, which returns them already laid out line by line — prose is how an
account number loses a digit.

---

## Repository layout

```
backend/           FastAPI app
  main.py          webhook + staff API routes
  config.py        env vars, validated at startup (fails loudly)
  handlers.py      what happens after the webhook returns 200
  outbound.py      the only place that decides text-vs-template and logs a send
  auth.py          staff (Supabase JWT) and device (X-Device-Token) principals
  whatsapp/        client.py (the only caller of Meta), parser.py, window.py, signature.py
  db/              all database access lives here
  agent/           graph.py, state.py, prompts.py, llm.py, tools/
  routes_public.py the unauthenticated catalogue kfoods.lk builds from
  routes_pos.py    the POS API, behind a device token
  routes_crm.py    the CRM API the dashboard calls, behind staff auth
  crm.py           pure customer arithmetic: segments, cadence, analytics
  catalog.py       catalogue payloads + ETags (public carries no stock)
  pricing.py       re-prices a basket from the catalogue; clients never decide
  phones.py        0771234567 / +94 77 ... -> 94771234567, one customer
  jobs/            auto-return background job
  tests/           268 tests, no network
dashboard/         Next.js App Router + Tailwind
  app/             overview, customers, inbox, orders, tasks, bills,
                   insights, products, inventory, login
  components/ui/   the design system: HeatBars, Icon, Bits (Stat, Chip, …)
  lib/crm.ts       stage colours, wording and the small client-side helpers
supabase/
  migrations/      0001_init.sql .. 0011_voice_and_receipts.sql (init, rls,
                   catalog, inventory, pos, crm, payments, voice and receipts)
  seed.sql         business row + message templates — run by hand
  seed_catalog.sql GENERATED: 90 product variants, business profile, 9 FAQs
data/              kfood-catalog.json, kfood-images.json — exported from the kfoods.lk site
assets/
  products/        20 product photos + index.json (which products still need one)
  brand/           logo, hero, og image, favicon
scripts/
  build_seed.py    data/kfood-catalog.json -> supabase/seed_catalog.sql
  mint_device_token.py  a credential for one POS terminal
```

## The catalogue

The source of truth is `data/kfood-catalog.json`, exported from the kfoods.lk static site
(`static/kfood`). It carries, per product: brand, Korean name, category, pack size, heat
level (0–5), cooking time, short and long descriptions, serving suggestion, ingredients,
allergens, nutrition, product URL, image, and three priced variants with SKUs.

| | |
|---|---|
| Products | 30 (Instant Noodles, Cup Noodles, Beverages) |
| SKUs | 90 — single, 5 Pack, carton of 20 |
| Brands | Nongshim, Migawon, Binggrae, OKF, Dong-A |
| Price range | Rs. 560 (Shin Ramyun Cup) – Rs. 17,900 (Shin Black carton) |
| Photos | 20 of 30 products; the other 10 show a placeholder on the site too |
| FAQs | 9, copied from the website so both channels answer the same way |

To refresh after the website changes:

```bash
cp ../kfood/rag-export/kfood-rag-data.json data/kfood-catalog.json
python3 scripts/build_seed.py          # rewrites supabase/seed_catalog.sql
# then run supabase/seed_catalog.sql in Supabase — it upserts, so re-running is safe
```

Products still without a photo: kimchi, cham-pong, chapagetti, ansung, hotdak-cheese,
toomba-cup, oncup-blue-lemon, oncup-blue-berry, oncup-green-grape, oncup-peach-iced-tea.
Drop a real photo into the website's `images/products/`, re-export, and re-run the steps
above.

---

## Setup

### 1. Supabase

1. Create a project (region: Singapore is closest to Sri Lanka).
2. SQL editor → run every file in `supabase/migrations/` in numeric order, `0001_init.sql`
   through `0011_voice_and_receipts.sql`. (`supabase/setup.sql` is an older one-paste bundle and
   stops at `0004`; it is not enough on its own.)
3. Edit the `vals` block at the top of `supabase/seed.sql`, run it, and copy the printed
   `business_id`.
4. Run `supabase/seed_catalog.sql` — the 90 SKUs, the business profile and the FAQs.
5. Create a staff user: Authentication → Users → Add user.
6. Link that user to the business (bottom of `seed.sql`):

   ```sql
   insert into business_members (business_id, user_id, role)
   values ('<business id>', '<auth user id>', 'admin');
   ```

   Without this row the dashboard signs in but shows nothing — RLS is doing its job.

### 2. Meta

1. developers.facebook.com → create an app → add the **WhatsApp** product.
2. Copy the test number's `phone_number_id` and the temporary access token.
3. Add your own phone under "To" as a test recipient (max 5).
4. App settings → Basic → copy the **App Secret** into `WA_APP_SECRET`.
5. Invent any string for `WA_VERIFY_TOKEN`; Meta must be given the same one.

### 3. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp ../.env.example ../.env     # then fill it in
.venv/bin/uvicorn main:app --reload --port 8000
```

`GET /health` should return `{"status": "ok", "database": "ok", ...}` and list any
production warnings.

### 4. Connect the webhook

```bash
ngrok http 8000
```

In the Meta app → WhatsApp → Configuration:

* **Callback URL**: `https://<your-ngrok-id>.ngrok-free.app/webhook`
* **Verify token**: the same `WA_VERIFY_TOKEN`
* Subscribe to the **messages** field.

Message the test number from your phone. You should get a reply within a few seconds.

### 5. Dashboard

```bash
cd dashboard
npm install
cp .env.local.example .env.local   # URL + publishable key + API URL
npm run dev                        # http://localhost:3000
```

Sign in with the staff user you created. `NEXT_PUBLIC_*` variables are public by
definition — never put the service role key or the WhatsApp token there.

---

## Environment variables

Backend — one file, `.env` in the repository root (see `.env.example`). `config.py`
resolves it by absolute path, so it loads whichever directory you start from.

Do not put a trailing `# comment` on a value line: python-dotenv keeps it as part of
the value, which silently breaks `LLM_PROVIDER`, `ENVIRONMENT` and `REQUIRE_AUTH`.


| Variable | Notes |
|---|---|
| `WA_ACCESS_TOKEN` | Temporary token for testing; a permanent System User token for production |
| `WA_PHONE_NUMBER_ID` | From the Meta dashboard |
| `WA_VERIFY_TOKEN` | Any random string; must match what Meta is given |
| `WA_APP_SECRET` | Verifies `X-Hub-Signature-256`. Required in production |
| `SUPABASE_URL` | Project origin only, e.g. `https://abc.supabase.co`. Pasting the REST URL (`.../rest/v1/`) 404s every query — config trims it, but paste it clean |
| `SUPABASE_SECRET_KEY` | `sb_secret_…`. Backend only, bypasses RLS. Legacy `SUPABASE_SERVICE_ROLE_KEY` still accepted |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_…`. Legacy `SUPABASE_ANON_KEY` still accepted |
| `SUPABASE_JWKS_URL` | `…/auth/v1/.well-known/jwks.json`. Verifies staff tokens locally (ES256), no call to Supabase per request |
| `SUPABASE_JWT_SECRET` | Legacy HS256 fallback, only if JWKS is not used |
| `LLM_PROVIDER` | `openrouter` by default. Also `gemini`, `openai`, `anthropic` |
| `OPENROUTER_API_KEY` | From https://openrouter.ai/keys |
| `OPENAI_API_KEY` | Required to transcribe WhatsApp voice notes, even when the chat model uses OpenRouter or Gemini |
| `VOICE_TRANSCRIPTION_MODEL` | OpenAI transcription model; defaults to `gpt-4o-mini-transcribe` |
| `VOICE_MAX_BYTES` | Maximum downloaded voice-note size; defaults to 10 MB and cannot exceed 25 MB |
| `VOICE_TRANSCRIPTION_TIMEOUT_SECONDS` | Per-request transcription timeout; defaults to 30 seconds |
| `LLM_MODEL` | Routed id, e.g. `google/gemini-3.1-flash-lite`. **Must support tool calling** — without it the agent cannot look up prices |
| `BUSINESS_ID` | The `businesses.id` from the seed |
| `AUTO_RETURN_MINUTES` | Human takeover expires after this many quiet minutes (default 30) |
| `ENVIRONMENT` | `production` makes startup refuse unresolved security warnings |
| `CORS_ORIGINS` | Comma-separated dashboard origins |
| `REQUIRE_AUTH` | Keep `true`. `false` leaves the staff API open — local smoke tests only |

---

## API

Public (Meta calls these):

| Method | Path | Purpose |
|---|---|---|
| GET | `/webhook` | Subscription handshake; returns `hub.challenge` as plain text |
| POST | `/webhook` | Message and status deliveries. Signature-checked, answers in milliseconds |
| GET | `/health` | Database state and production warnings |

Staff (Bearer token from Supabase Auth, must be in `business_members`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/messages/send` | Staff reply. Takes the chat over by default |
| POST | `/messages/send-template` | Send an approved template (used when the window is closed) |
| POST | `/contacts/{id}/takeover` | Agent ⇄ human switch |
| POST | `/contacts/{id}/read` | Clear the unread badge |
| GET | `/contacts/{id}/window` | Time left in the 24-hour window |
| GET | `/contacts`, `/orders`, `/templates` | Lists |
| PATCH | `/orders/{id}/status` | Change status and notify the customer |
| PATCH | `/orders/{id}/payment` | Mark an order paid, unpaid or refunded (staff only) |
| GET | `/stats/usage` | Messages sent this month |
| GET | `/inventory`, `/inventory/movements` | Stock levels and the ledger behind them |
| GET | `/devices` | The POS terminals, live and revoked |
| POST | `/devices` | Mint a device token. The raw token is returned **once** |
| POST | `/devices/{id}/revoke` | Make a lost shop Mac useless |

CRM (same staff auth, mounted under `/crm`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/crm/customers` | The customer book. Each row carries the stats its orders imply |
| GET | `/crm/customers/{id}` | One customer: orders, notes, follow-ups, bills, recent messages |
| PATCH | `/crm/customers/{id}` | A staff edit. Only the fields sent are written |
| POST | `/crm/customers/{id}/notes` | Add a note. The agent reads these when it answers |
| PATCH | `/crm/notes/{id}` | Pin or unpin a note |
| GET/POST | `/crm/tasks` | Follow-ups, soonest due first |
| PATCH | `/crm/tasks/{id}` | Edit one, or tick it off |
| GET | `/crm/analytics?days=` | Revenue by day, best sellers, new vs returning, the mix |
| GET | `/crm/invoices` | The printed POS bills, staff-side |
| POST | `/crm/invoices/{id}/review` | Record that a human looked at a price mismatch |

Nothing under `/crm` sends a message, moves stock or changes an order's status —
those have owners already, and a second path to them is a second place for them
to go wrong. Nothing under `/crm` stores a derived figure either: lifetime
value, segment and every chart are computed from `orders` on each read by
`crm.py`, so a number on screen can always be traced back to the orders behind
it.

Public, unauthenticated (kfoods.lk builds itself from these):

| Method | Path | Purpose |
|---|---|---|
| GET | `/public/catalog` | Products, prices and the store block. ETag + `max-age=300` |
| GET | `/public/availability` | In stock or out, per SKU. Never a number. `max-age=60` |

Neither carries stock levels, customers or orders — only a boolean per SKU. An
exact count would tell a competitor the shop's sales volume.

`track_stock` is **already on for all 30 products**, each seeded with a
placeholder of 1000 singles on 18 September 2026. So availability is live, not
dormant: nothing reports `out_of_stock` today only because the quantities are
high. The first real stocktake that replaces those placeholders is the moment a
product can start reporting `out_of_stock` — and once the website consumes this
(Phase 3), that reaches `schema.org` Offer markup, where a wrong count has an
SEO consequence it never had before.

POS (`X-Device-Token`, minted per device — see below):

| Method | Path | Purpose |
|---|---|---|
| GET | `/pos/catalog` | The catalogue **with** stock. The till caches it and revalidates by ETag |
| GET | `/pos/orders` | Open orders with the customer attached, ready to print |
| GET | `/pos/orders/{id}` | One order and the bills already printed for it |
| GET | `/pos/contacts/lookup?phone=` | Resolve a phone. Read-only — never creates a contact |
| POST | `/pos/bills` | Record a printed bill. The only write |

---

## The POS

K FOOD is online only, so the POS is not a till: it prints the invoice that goes
in the courier parcel for an order that arrived on WhatsApp. Two rules hold it
in place.

**It never moves stock.** Printing paper is not what takes a pack off the shelf —
confirming the order is, and `PATCH /orders/{id}/status` already does that. A
bill leaves `menu_items.stock_quantity` untouched.

**It never decides a price.** The till sends SKUs and quantities; `pricing.py`
prices them from `menu_items`, exactly as the agent's `create_order` does. A till
that has been offline for a week cannot move money.

When the two disagree — an offline till printed at last week's price — **both
figures are kept**. `order_invoices` stores what the paper said and what the
catalogue says, flags `mismatch`, and writes a line into the order's notes where
staff will read it. Paper is the contract with the customer; the database is the
shop's record; neither silently overwrites the other.

### Device tokens

The till holds a credential on a machine several people use, so it is not a staff
login. It is minted per device, reaches `/pos/*` and nothing else, and **cannot
send a WhatsApp message to a customer**. That is structural rather than a
convention: staff auth reads `Authorization` and device auth reads
`X-Device-Token`, so neither credential can satisfy the other's dependency.

```bash
backend/.venv/bin/python scripts/mint_device_token.py \
    --device-id MAC1 --name "Shop Mac — counter"
```

The raw token is printed once; only its sha256 is stored. Lost it? Revoke the row
and mint another — there is no recovery, which is the point.

`MAC1` is also printed into every bill number that device issues
(`KF-MAC1-20260919-003`). That prefix is what stops two shop Macs both issuing
`-001` on the same day, and it is what makes a replayed bill safe to ignore: the
bill number is the idempotency key for the till's offline queue.

---

## The LLM

The agent talks to OpenRouter, which speaks the OpenAI API, so one wrapper
([agent/llm.py](backend/agent/llm.py)) serves every provider and swapping model is an env
change, not a code change.

The model **must support tool calling**. Prices, orders, delivery terms and allergens all
come from tools; a model that cannot call them has nothing truthful to say. Verified
against OpenRouter's live model list (per 1M tokens, input/output):

| Model | Cost | Notes |
|---|---|---|
| `google/gemini-3.1-flash-lite` | $0.25 / $1.50 | default — 1M context, cheap, reliable tool calls |
| `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | cheapest sensible option |
| `openai/gpt-4o-mini` | $0.15 / $0.60 | alternative if Gemini misbehaves on Sinhala |
| `google/gemini-2.5-flash` | $0.30 / $2.50 | strongest of these, if replies need more judgement |

A typical reply costs roughly 5–7k input tokens (system prompt, catalogue results, last
10 turns) and ~100 output. The system prompt is about 3.9k of that: it grew when the
scope guardrails went in, and that is the deliberate trade — the rules that stop the
agent answering general-knowledge questions and switching itself off are the ones being
paid for. Trim the "Situations you will meet" section first if the bill matters more.

To use Gemini directly instead, set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY`, and change
`LLM_MODEL` to a bare id like `gemini-2.0-flash`.

## The rules this code enforces

* **One reply per message.** The prompt forbids splitting, and only one send happens per
  inbound message. Every message costs money.
* **Idempotency.** `messages.wa_message_id` is unique and checked before the agent runs.
  Meta retries; customers must not get two answers.
* **The 24-hour window.** `outbound.py` checks it before every send. Outside it, free text
  is refused and an approved template is sent instead. The dashboard shows a countdown and
  swaps the text box for template buttons when it expires.
* **Human takeover.** While it is on, inbound messages are stored but the agent never
  answers. A background job hands the chat back after `AUTO_RETURN_MINUTES` of silence.
* **No invented prices.** Tools read the catalogue; `create_order` prices each SKU from the
  database, adds the delivery fee, and refuses SKUs that do not exist.
* **No invented facts.** Delivery, payment, returns and contact answers come from the
  business profile and the FAQ table via `store_info`.
* **"Ramen" finds "Ramyun".** Catalogue search expands the words Sri Lankan customers
  actually type (ramen, ramyeon, buldak, fire noodles, drinks, juice, cup) — without it,
  a search for "ramen" returned 3 products instead of 16.
* **The agent talks like a person, not a queue.** No "staff will confirm", no "a team
  member will get back to you", no describing itself as an assistant or a bot. It answers
  in the first person because that is how a shop assistant answers. Asked outright whether
  it is a person or a bot, it tells the truth in one line and carries on — sounding human
  is not the same as claiming to be human, and the prompt draws that line explicitly.
* **A slip is not a payment.** The agent cannot open the image a customer sends. When one
  arrives it calls `record_payment_receipt`, which moves the order to `receipt_received`,
  writes what the customer said into `payment_note` and puts a high-priority task on the
  list. Only `PATCH /orders/{id}/payment` — a person, in the dashboard — can say
  `verified`. The prompt forbids the agent from ever telling a customer the money arrived.
* **An attachment does not end the conversation.** A photo used to mean a silent takeover
  and a canned "I can't open attachments". Most of them are bank slips, so that reply
  dropped a paying customer mid-sale. Media now reaches the agent marked as unreadable in
  its history and it works out what to do — take the slip, ask what the product is, or
  escalate a complaint. Stickers are still ignored: paying for a reply to a thumbs-up is
  money spent on nothing.
* **Recommendations come from the catalogue, with their reasons.** `suggest_products`
  scores every product against the taste the customer described — heat band, soup or stir
  fry, budget, what to avoid — and hands back the reason each one matched, so the reply can
  say *why* rather than reading out a list. It never recommends what is out of stock, and
  never a 5/5 to somebody who asked for mild.
* **The shop, and nothing but the shop.** The agent answers about K FOOD's food, prices,
  stock, deliveries, orders and payments. General knowledge, politics, news, homework,
  medical or legal advice, other shops — declined in one warm line and turned back to the
  food, and the decline holds when the customer pushes. It had been answering who the
  president of Sri Lanka was, and giving up the longest river in the world on the second
  ask. Nothing outside the shop is ever treated as work for a person, because that is how
  a customer ends up waiting for a reply nobody is coming to write.
* **Two ways to involve a person, and only one of them is silence.** These were a single
  tool, which meant every "someone should look at this" also switched the agent off:
  `flag_for_staff` puts a task on the list and the agent **keeps selling**; it covers
  wholesale, adding to an existing order, a promised date, a question it genuinely cannot
  answer. `escalate_to_human` hands the conversation over and the agent **stops** — a
  complaint, a refund, money gone wrong, a wrong or damaged order, abuse, an allergy
  question `product_details` cannot answer. When the model is unsure, the prompt sends it
  to the softer one, because a customer still being served can be handed over a minute
  later and a customer switched off is just waiting.
* **A chat under takeover still answers once.** Silence is not a neutral act: a customer
  wrote "I need shin red one noodles packet", then "Please reply", into a chat nobody had
  picked up, and got nothing. The agent stays out of a chat a person owns, but the number
  replies once — and only once, judged by whether anything at all has gone out since the
  takeover started, so a staff reply suppresses it and three messages do not produce three
  apologies.
* **A segment is a suggestion, never a decision.** `crm.suggest_lifecycle` reads the
  orders; a staff member sets the stage on the record. The dashboard shows when the two
  disagree and offers the change. Orders do not know that a customer moved to Dubai.
* **Silence is judged against the customer's own cadence.** Somebody who orders every
  Friday and has not been seen for three weeks is at risk; somebody who orders twice a
  year and is three weeks late is not. A fixed "dormant after 60 days" rule gets both
  wrong, and the one it gets wrong loudest is the regular nobody chases.
* **Reviewing a printed bill is not correcting it.** `POST /crm/invoices/{id}/review`
  records that a human looked. The paper in the parcel is the only evidence of what the
  customer was actually charged, and nothing rewrites it.

---

## Tests

```bash
cd backend && .venv/bin/pytest        # 302 tests, no network calls
cd dashboard && npm run typecheck && npm run lint && npm run build
```

The suite covers the parser against real Meta payload shapes, window arithmetic,
signature verification, idempotency, the inbound pipeline (dedupe, takeover, media),
graph wiring with a stubbed model, the outbound policy, and the HTTP surface.

`tests/test_crm.py` is in two halves. The first hands `crm.py` lists of orders and
pins down every segment rule — a cancelled order counts but is not charged for, a
big spender who has gone quiet is at risk rather than a VIP, a chart keeps the days
nobody ordered. The second drives the HTTP surface, including the two rules worth
proving: a staff edit cannot reach `unread_count` or the 24-hour window, and a POS
device token cannot read the customer book at all.

---

## Deploy

**Backend — Fly.io** (kept for reference; production moved to Railway below)

```bash
cd backend
fly launch --no-deploy            # uses fly.toml
fly secrets set WA_ACCESS_TOKEN=... WA_PHONE_NUMBER_ID=... WA_VERIFY_TOKEN=... \
                WA_APP_SECRET=... SUPABASE_URL=... SUPABASE_SECRET_KEY=... \
                SUPABASE_PUBLISHABLE_KEY=... SUPABASE_JWKS_URL=... \
                OPENROUTER_API_KEY=... BUSINESS_ID=... \
                ENVIRONMENT=production CORS_ORIGINS=https://your-dashboard.vercel.app
fly deploy
```

**Backend — Railway (this is what production runs).** Hobby plan, Singapore, one
replica, no serverless sleep, at `https://kfoodagent-dimuthu-production.up.railway.app`.

`railway.json` is **not** read: Config as Code is closed to services created after
2026-08-28, so builder, start command and healthcheck are set in the service UI.
Root Directory is `backend` and watch paths are **cleared** — watch paths resolve
against the Root Directory, so `/backend/**` matches nothing and pushes silently
stop deploying. Leave them cleared.

A push to `main` deploys. `main.py:lifespan` refuses to start in production if
`check_production_readiness()` returns anything, so a container that booted has
already proved its CORS, token and key config are clean — check `/health` and
look for `warnings: []`.

Run **one instance**. The auto-return job and the per-contact locks are in-process; more
than one replica means duplicate jobs. Scaling out means moving both into Postgres first.

**Dashboard — Cloudflare Pages (this is what production runs).** Connected to this
GitHub repo, root directory `dashboard`, build `npm run build`, output `out`. `out/`
is gitignored on purpose; Pages builds it. `public/_headers` is copied into the
output and applied at the edge.

The same push therefore deploys **both**. They do not finish together, so expect a
minute or two where the dashboard is live against a backend that has not restarted
yet — every page shows its own error text and a Try again button for that window,
and nothing is lost.

`NEXT_PUBLIC_API_URL` **must carry `https://`**. Without a scheme `fetch()` treats it
as a relative path and the browser asks Cloudflare for
`kfoodagent.pages.dev/kfoodagent-…up.railway.app/crm/customers`, which 404s.

Any new dashboard origin has to be added to `CORS_ORIGINS` on the backend, or every
request from it fails with nothing useful in the console.

Then point the Meta webhook at `https://<backend-host>/webhook`.

---

## Go-live checklist

- [ ] New SIM added as a real phone number in the Meta app and verified (**not** the number
      on the WhatsApp Business App — Cloud API takes the number over)
- [ ] Meta Business Verification complete
- [ ] Permanent System User token in `WA_ACCESS_TOKEN` (the temporary one dies in 24 hours)
- [ ] `0002_rls.sql` applied; `select * from pg_tables where rowsecurity = false` shows nothing public
- [ ] `WA_APP_SECRET` set; `/health` lists no warnings
- [ ] `ENVIRONMENT=production` (startup then refuses to run with warnings)
- [ ] Templates submitted to Meta, approved, and flipped to `approved = true` in `templates`
- [ ] `seed_catalog.sql` run, and `select count(*) from menu_items` returns 90
- [ ] Prices in `menu_items` still match kfoods.lk (re-run the export if the site changed)
- [ ] Staff users added to `business_members`
- [ ] Webhook URL points at production and the **messages** field is subscribed
- [ ] New number on the website, Google profile and Facebook page

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Customer gets two replies | More than one backend instance, or the unique index on `wa_message_id` is missing |
| Webhook returns 403 | `WA_VERIFY_TOKEN` mismatch, or `WA_APP_SECRET` does not match the app |
| Agent silent, messages stored | `human_takeover` is on — check the toggle, or wait for auto-return |
| Sends fail with code 131047 | The 24-hour window closed. Use a template |
| Dashboard signs in but is empty | The user is missing from `business_members` |
| Every query 404s with "schema cache" | The migrations have not been run, or `SUPABASE_URL` includes `/rest/v1` |
| `template_unavailable` | The template row is missing or `approved` is still false |
| Agent says a product is not on the catalogue | `seed_catalog.sql` was not run, or the site renamed it |
| Startup exits immediately | A required variable is missing; the error names it |

---

## Costs

From 1 October 2026 Meta charges for service messages and utility templates sent inside
the 24-hour window, with the first 1,000 service messages per number per month free. That
is why the agent answers in exactly one message. The dashboard header shows the running
monthly count.
