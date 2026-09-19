-- 0006_pos.sql — the POS becomes part of the system.
--
-- The POS is not a till. K FOOD is online only: every order arrives through
-- WhatsApp, and the POS prints the invoice that goes in the courier parcel.
-- So every bill has a WhatsApp customer behind it, which is why orders.contact_id
-- stays NOT NULL here — nothing about this migration relaxes it.
--
-- Three things arrive:
--   * device_tokens   — a machine principal, so the shop Mac can reach the API
--                       without holding a staff login that could message customers
--   * orders columns  — discount, provenance, and an idempotency key for the
--                       POS's offline outbox
--   * order_invoices  — evidence that a piece of paper exists, kept separately
--                       from the order's own state
--
-- Deliberately NOT here: any change to stock. Printing an invoice is inventory-
-- neutral. Stock still moves only when staff set an order to 'confirmed', which
-- is what 0005 wired to inventory.sell_order().

-- ---------------------------------------------------------------------------
-- device_tokens — a principal that is a machine, not a person
-- ---------------------------------------------------------------------------
-- It has no Supabase Auth identity, no email and no business_members row. It
-- reaches the catalogue and the order routes and nothing else, so a token left
-- on a shared shop Mac cannot send a WhatsApp message to a customer.
create table if not exists device_tokens (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,

  -- Short, uppercase, and printed into every bill number this device issues
  -- (KF-MAC1-20260919-003). That prefix is what stops two devices both
  -- issuing -001 on the same day, which is the collision the POS has today.
  device_id text not null check (device_id ~ '^[A-Z0-9]{2,6}$'),
  name text not null,                      -- "Shop Mac — counter"

  -- The first characters of the raw token, stored in clear on purpose: it is
  -- how a log line or the dashboard names a token without holding the secret.
  token_prefix text not null,

  -- sha256 of the raw token, hex. Not bcrypt or argon2 deliberately: the token
  -- is 256 bits of CSPRNG output, so an offline attack on the hash is not the
  -- threat model, and a per-row salt would turn every request into a table
  -- scan instead of a unique-index lookup.
  token_hash text not null unique,

  -- Not enforced at the route level today — every device gets the same pair and
  -- that is the whole /pos surface. It exists so a future read-only device is a
  -- data change rather than a code change.
  scopes text[] not null default '{catalog,orders}',

  revoked_at timestamptz,
  revoked_by text,
  last_seen_at timestamptz,                -- "is this device still alive?"
  created_by text not null default 'owner',
  created_at timestamptz not null default now(),

  unique (business_id, device_id)
);

create index if not exists device_tokens_live_idx
  on device_tokens (business_id) where revoked_at is null;

-- ---------------------------------------------------------------------------
-- orders — three facts it could not previously hold
-- ---------------------------------------------------------------------------

-- The POS discount is a real money movement with nowhere to live: without it
-- total <> subtotal + delivery and nobody can explain the gap.
alter table orders add column if not exists discount numeric(10, 2) not null default 0
  check (discount >= 0);

-- pos.js stores only the derived rupee figure, so a bill discounted "10%" keeps
-- no trace of the intent. Staff reading an order a week later should see which
-- it was.
alter table orders add column if not exists discount_note text;

-- Which surface created this row. POS orders arrive with paper already printed
-- and are inventory-neutral until confirmed, so they need to be distinguishable.
-- 'agent' is the correct default for every row that already exists.
alter table orders add column if not exists source text not null default 'agent'
  check (source in ('agent', 'pos', 'dashboard', 'web'));

-- The idempotency anchor for the POS's offline outbox: the device-prefixed bill
-- number of the bill that created this order. A retried POST finds this row
-- instead of creating a second one. Partial, so agent-created rows (null) are
-- untouched and can stay null forever.
alter table orders add column if not exists external_ref text;

create unique index if not exists orders_business_external_ref_key
  on orders (business_id, external_ref) where external_ref is not null;

create index if not exists orders_source_created_idx
  on orders (business_id, source, created_at desc);

-- ---------------------------------------------------------------------------
-- order_invoices — what the paper says
-- ---------------------------------------------------------------------------
-- A separate table rather than columns on orders, because a bill is evidence
-- that a piece of paper exists, not order state. One order can be printed more
-- than once (a reprint, a corrected copy), and the printed figures must survive
-- even when the catalogue later prices the same basket differently.
--
-- That is the rule this table encodes: the paper is the contract with the
-- customer, the database is the shop's record, and neither silently overwrites
-- the other. Both sets of figures are stored side by side and a mismatch is
-- raised for a human rather than resolved by guessing.
create table if not exists order_invoices (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  order_id uuid not null references orders(id) on delete cascade,

  device_id text not null,
  bill_no text not null,                   -- KF-MAC1-20260919-003
  printed_at timestamptz not null,         -- the DEVICE clock, when paper came out
  received_at timestamptz not null default now(),   -- when it reached the server

  -- What the paper says. Never recomputed, never corrected.
  paper_subtotal numeric(10, 2) not null,
  paper_discount numeric(10, 2) not null default 0,
  paper_tax      numeric(10, 2) not null default 0,
  paper_delivery numeric(10, 2) not null default 0,
  paper_total    numeric(10, 2) not null,

  -- What the catalogue says the same basket costs, computed server-side.
  server_subtotal numeric(10, 2) not null,
  server_discount numeric(10, 2) not null default 0,
  server_tax      numeric(10, 2) not null default 0,
  server_delivery numeric(10, 2) not null default 0,
  server_total    numeric(10, 2) not null,

  mismatch boolean not null default false,
  mismatch_detail jsonb not null default '[]',   -- [{sku, printed, server, reason}]
  reviewed_at timestamptz,
  reviewed_by text,

  payment_method text,                     -- print-time label, not a payment record
  catalog_version text,                    -- the ETag the device priced from
  lines jsonb not null default '[]',       -- exactly what was printed, custom lines included
  created_by text not null,                -- "pos:MAC1"

  -- The real idempotency anchor. It covers both cases with one constraint:
  -- creating an order from a bill, and printing a bill for an order the agent
  -- already made.
  unique (business_id, bill_no)
);

create index if not exists order_invoices_order_idx on order_invoices (order_id);

-- The review queue: bills whose paper and catalogue disagree and that nobody
-- has looked at yet.
create index if not exists order_invoices_review_idx
  on order_invoices (business_id, printed_at desc)
  where mismatch and reviewed_at is null;

-- ---------------------------------------------------------------------------
-- Row Level Security — same model as every other table (see 0002_rls.sql)
-- ---------------------------------------------------------------------------

-- RLS on, and deliberately NO policy. 0002's model is "staff read, backend
-- writes", but a token hash and its prefix have no business in a browser bundle
-- even read-only. RLS enabled with no policy denies `authenticated` entirely;
-- the service role key bypasses it, which is how the backend reads the table.
-- The dashboard lists and revokes devices through the backend, like everything
-- else it cannot do directly.
alter table device_tokens enable row level security;

alter table order_invoices enable row level security;

drop policy if exists order_invoices_select_member on order_invoices;
create policy order_invoices_select_member on order_invoices
  for select to authenticated
  using (public.is_business_member(business_id));

-- Not added to supabase_realtime on purpose: the dashboard polls this on the
-- orders view, and a subscription would be one more moving part for a table
-- that changes a few times a day.
