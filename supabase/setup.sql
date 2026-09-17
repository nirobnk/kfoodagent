-- setup.sql — GENERATED. Everything except the product catalogue, in one paste.
--
-- Paste this whole file into the Supabase SQL editor and run it. The last
-- statement prints the business_id — copy it into BUSINESS_ID in .env.
-- Then run supabase/seed_catalog.sql (120 KB) as a second paste.
--
-- Safe to re-run: every statement is create-if-not-exists or an upsert.

-- ===== migrations/0001_init.sql ===========================================
-- 0001_init.sql — base schema for the K-Food WhatsApp agent + CRM.
-- Multi-tenant rule: every table carries business_id from day one.
-- Applied migrations are never edited; add a new numbered file instead.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- businesses (tenants)
-- ---------------------------------------------------------------------------
create table if not exists businesses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  wa_phone_number_id text not null,
  timezone text not null default 'Asia/Colombo',
  currency text not null default 'LKR',
  created_at timestamptz not null default now()
);

-- Maps a Supabase Auth user to the tenant whose rows they may read.
-- Needed by the RLS policies in 0002; the backend uses the service role key
-- and bypasses all of this.
create table if not exists business_members (
  business_id uuid not null references businesses(id) on delete cascade,
  user_id uuid not null,
  role text not null default 'staff' check (role in ('staff', 'admin')),
  created_at timestamptz not null default now(),
  primary key (business_id, user_id)
);

-- ---------------------------------------------------------------------------
-- contacts (customers)
-- ---------------------------------------------------------------------------
create table if not exists contacts (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  wa_id text not null,                          -- customer phone, e.g. 94771234567
  name text,
  language text default 'en',                   -- en | si | ta
  tags text[] not null default '{}',
  human_takeover boolean not null default false,
  takeover_started_at timestamptz,
  takeover_by text,
  last_customer_message_at timestamptz,         -- drives the 24-hour window
  unread_count integer not null default 0,
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  unique (business_id, wa_id)
);

-- ---------------------------------------------------------------------------
-- messages
-- ---------------------------------------------------------------------------
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  contact_id uuid not null references contacts(id) on delete cascade,
  direction text not null check (direction in ('in', 'out')),
  sender text not null check (sender in ('customer', 'agent', 'human', 'system')),
  body text,
  media_url text,
  message_type text not null default 'text',    -- text | image | audio | document | template | interactive
  template_name text,                           -- set when sent outside the 24h window
  wa_message_id text unique,                    -- Meta's id. Drives idempotency.
  status text not null default 'sent'
    check (status in ('queued', 'sent', 'delivered', 'read', 'failed')),
  error text,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- orders
-- ---------------------------------------------------------------------------
create table if not exists orders (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  contact_id uuid not null references contacts(id) on delete cascade,
  order_number serial,
  items jsonb not null default '[]',
  total numeric(10, 2) not null default 0,
  status text not null default 'new'
    check (status in ('new', 'confirmed', 'preparing', 'dispatched', 'delivered', 'cancelled')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- notes (CRM memory the agent writes and reads)
-- ---------------------------------------------------------------------------
create table if not exists notes (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  contact_id uuid not null references contacts(id) on delete cascade,
  note text not null,
  created_by text not null default 'agent',
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- menu_items
-- ---------------------------------------------------------------------------
create table if not exists menu_items (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  name text not null,
  description text,
  price numeric(10, 2) not null,
  category text,
  available boolean not null default true,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- templates — approved Meta templates, with their variable order, so the
-- application code never hardcodes a template body.
-- ---------------------------------------------------------------------------
create table if not exists templates (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  key text not null,                            -- internal key, e.g. order_confirmed
  name text not null,                           -- name registered with Meta
  language text not null default 'en',
  category text not null default 'UTILITY',
  variables text[] not null default '{}',       -- ordered placeholder names
  body_preview text,
  approved boolean not null default false,
  created_at timestamptz not null default now(),
  unique (business_id, key)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index if not exists messages_contact_created_idx on messages (contact_id, created_at desc);
create index if not exists messages_business_created_idx on messages (business_id, created_at desc);
create index if not exists orders_business_status_idx on orders (business_id, status, created_at desc);
create index if not exists orders_contact_created_idx on orders (contact_id, created_at desc);
create index if not exists contacts_business_lastseen_idx on contacts (business_id, last_seen desc);
create index if not exists contacts_takeover_idx on contacts (human_takeover, takeover_started_at);
create index if not exists notes_contact_created_idx on notes (contact_id, created_at desc);
create index if not exists menu_items_business_idx on menu_items (business_id, available);

-- ---------------------------------------------------------------------------
-- orders.updated_at is maintained by the database, not the application.
-- ---------------------------------------------------------------------------
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists orders_set_updated_at on orders;
create trigger orders_set_updated_at
  before update on orders
  for each row execute function set_updated_at();

-- ===== migrations/0002_rls.sql ============================================
-- 0002_rls.sql — Row Level Security.
--
-- Model:
--   * The backend uses the service role key and bypasses RLS entirely.
--     Every write in this system goes through the backend.
--   * The dashboard uses the anon key + Supabase Auth. Signed-in staff get
--     read-only access to the rows of the business they belong to.
--
-- Never ship without this file applied.

alter table businesses       enable row level security;
alter table business_members enable row level security;
alter table contacts         enable row level security;
alter table messages         enable row level security;
alter table orders           enable row level security;
alter table notes            enable row level security;
alter table menu_items       enable row level security;
alter table templates        enable row level security;

-- Helper: is the current auth user a member of this business?
-- security definer so the lookup itself is not subject to RLS (avoids recursion).
create or replace function public.is_business_member(target uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from business_members m
    where m.business_id = target
      and m.user_id = auth.uid()
  );
$$;

revoke all on function public.is_business_member(uuid) from public;
grant execute on function public.is_business_member(uuid) to authenticated;

-- businesses: a member can see their own tenant row.
drop policy if exists businesses_select_member on businesses;
create policy businesses_select_member on businesses
  for select to authenticated
  using (public.is_business_member(id));

-- business_members: a user can see their own membership rows.
drop policy if exists business_members_select_self on business_members;
create policy business_members_select_self on business_members
  for select to authenticated
  using (user_id = auth.uid());

-- Tenant-scoped read access for every operational table.
do $$
declare
  t text;
begin
  foreach t in array array['contacts', 'messages', 'orders', 'notes', 'menu_items', 'templates']
  loop
    execute format('drop policy if exists %I on %I', t || '_select_member', t);
    execute format(
      'create policy %I on %I for select to authenticated using (public.is_business_member(business_id))',
      t || '_select_member', t
    );
  end loop;
end;
$$;

-- No insert/update/delete policies exist on purpose: the dashboard writes
-- nothing directly. It calls the backend, which holds the WhatsApp token and
-- the service role key.

-- Realtime: the dashboard subscribes to these tables.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    begin
      alter publication supabase_realtime add table messages;
    exception when duplicate_object then null;
    end;
    begin
      alter publication supabase_realtime add table contacts;
    exception when duplicate_object then null;
    end;
    begin
      alter publication supabase_realtime add table orders;
    exception when duplicate_object then null;
    end;
  end if;
end;
$$;

-- Realtime sends the full row only when the replica identity carries it.
alter table messages replica identity full;
alter table contacts replica identity full;
alter table orders   replica identity full;

-- ===== migrations/0003_functions.sql ======================================
-- 0003_functions.sql — small server-side helpers.

-- Atomic unread counter. Called by the backend when a customer message lands;
-- a read-modify-write from the application would lose counts under retries.
create or replace function public.bump_unread(p_contact_id uuid)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  new_count integer;
begin
  update contacts
     set unread_count = unread_count + 1
   where id = p_contact_id
  returning unread_count into new_count;
  return coalesce(new_count, 0);
end;
$$;

revoke all on function public.bump_unread(uuid) from public;
-- Only the service role (the backend) may call it.
grant execute on function public.bump_unread(uuid) to service_role;

-- ===== migrations/0004_catalog.sql ========================================
-- 0004_catalog.sql — the real kfoods.lk catalog.
--
-- K FOOD is an online Korean grocery store, not a restaurant kitchen: every
-- product is sold in three variants (single / 5 Pack / carton of 20) at
-- different prices, and customers ask about heat level, allergens and cooking
-- instructions. One row per *variant*, grouped by `handle`, so the agent can
-- quote an exact price for exactly what the customer asked for.

-- --------------------------------------------------------------------------
-- menu_items becomes the product catalogue
-- --------------------------------------------------------------------------
alter table menu_items add column if not exists handle text;              -- product id, shared by its variants
alter table menu_items add column if not exists sku text;                 -- e.g. RAM-SHIN-5
alter table menu_items add column if not exists product_name text;        -- "Shin Ramyun Original"
alter table menu_items add column if not exists variant_label text;       -- "5 Pack"
alter table menu_items add column if not exists units integer default 1;  -- packs per variant
alter table menu_items add column if not exists unit_price numeric(10, 2);
alter table menu_items add column if not exists brand text;
alter table menu_items add column if not exists korean_name text;
alter table menu_items add column if not exists pack_size text;           -- "120g"
alter table menu_items add column if not exists heat_level smallint;      -- 0-5, null for drinks
alter table menu_items add column if not exists cook_time text;
alter table menu_items add column if not exists badge text;               -- "Best Seller"
alter table menu_items add column if not exists short_description text;
alter table menu_items add column if not exists long_description text;
alter table menu_items add column if not exists serving_suggestion text;
alter table menu_items add column if not exists ingredients text;
alter table menu_items add column if not exists allergens text;
alter table menu_items add column if not exists nutrition jsonb default '{}';
alter table menu_items add column if not exists image_url text;           -- https://kfoods.lk/...
alter table menu_items add column if not exists image_file text;          -- repo path, null when no photo exists
alter table menu_items add column if not exists product_url text;
alter table menu_items add column if not exists sort_order integer default 0;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'menu_items_business_sku_key') then
    alter table menu_items add constraint menu_items_business_sku_key unique (business_id, sku);
  end if;
end;
$$;

create index if not exists menu_items_handle_idx on menu_items (business_id, handle);
create index if not exists menu_items_brand_idx on menu_items (business_id, brand);

-- --------------------------------------------------------------------------
-- Everything else the agent must know about the business: delivery fee, free
-- delivery threshold, bank details, returns policy, contact, how to order.
-- One jsonb column keeps this multi-tenant without a column per fact.
-- --------------------------------------------------------------------------
alter table businesses add column if not exists profile jsonb not null default '{}';

-- --------------------------------------------------------------------------
-- FAQs, straight from the website, so answers on the phone match answers online
-- --------------------------------------------------------------------------
create table if not exists faqs (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  question text not null,
  answer text not null,
  tags text[] not null default '{}',
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  unique (business_id, question)
);

create index if not exists faqs_business_idx on faqs (business_id, sort_order);

alter table faqs enable row level security;

drop policy if exists faqs_select_member on faqs;
create policy faqs_select_member on faqs
  for select to authenticated
  using (public.is_business_member(business_id));

-- --------------------------------------------------------------------------
-- Orders carry delivery separately: LKR 400 island-wide, free over LKR 5,000.
-- --------------------------------------------------------------------------
alter table orders add column if not exists subtotal numeric(10, 2) not null default 0;
alter table orders add column if not exists delivery_fee numeric(10, 2) not null default 0;

-- ===== seed.sql =========================================================
-- seed.sql — run once, by hand, in the Supabase SQL editor.
-- Not a migration: it contains tenant data, not schema.
--
-- Order of operations:
--   1. migrations 0001 → 0004
--   2. this file      (creates the business row and the message templates)
--   3. seed_catalog.sql (the real kfoods.lk catalogue, generated)
--
-- Edit `wa_phone_number_id` below, run the file, and copy the printed id into
-- BUSINESS_ID in the backend environment.

with vals as (
  select
    'K FOOD'::text      as name,
    'REPLACE_ME'::text  as wa_phone_number_id   -- Meta test number id for now
),
upsert as (
  insert into businesses (name, wa_phone_number_id)
  select name, wa_phone_number_id from vals
  where not exists (select 1 from businesses b where b.name = (select name from vals))
  returning id
)
select coalesce(
  (select id from upsert),
  (select id from businesses where name = (select name from vals))
) as business_id;

-- --------------------------------------------------------------------------
-- Message templates. `name` must match what Meta approved, exactly.
-- `variables` is the ordered placeholder list: {{1}}, {{2}}, {{3}}.
-- Flip `approved` to true once Meta approves each one.
-- --------------------------------------------------------------------------
insert into templates (business_id, key, name, language, category, variables, body_preview, approved)
select b.id, v.key, v.name, 'en', 'UTILITY', v.variables, v.body_preview, false
from businesses b
cross join (values
  ('order_confirmed', 'order_confirmed', array['customer_name', 'order_number', 'total'],
   'Hello {{1}}, your K FOOD order #{{2}} is confirmed. Total Rs. {{3}}.'),
  ('order_dispatched', 'order_dispatched', array['customer_name', 'order_number'],
   'Hello {{1}}, your K FOOD order #{{2}} is on the way.'),
  ('order_delivered', 'order_delivered', array['order_number'],
   'Order #{{1}} delivered. Thank you for choosing K FOOD!')
) as v(key, name, variables, body_preview)
where b.name = 'K FOOD'
on conflict (business_id, key) do nothing;

-- --------------------------------------------------------------------------
-- The catalogue lives in seed_catalog.sql — 30 products, 90 variants, and the
-- delivery / payment / returns profile, generated from the kfoods.lk export by
-- `python3 scripts/build_seed.py`. Run that file next.
-- --------------------------------------------------------------------------

-- --------------------------------------------------------------------------
-- Give a staff member dashboard access (repeat per user).
-- Find the user id in Supabase -> Authentication -> Users.
-- --------------------------------------------------------------------------
-- insert into business_members (business_id, user_id, role)
-- select id, '00000000-0000-0000-0000-000000000000', 'admin' from businesses where name = 'K FOOD'
-- on conflict do nothing;

-- ===========================================================================
-- Copy this value into BUSINESS_ID in .env
-- ===========================================================================
select id as business_id, name, created_at from businesses where name = 'K FOOD';
