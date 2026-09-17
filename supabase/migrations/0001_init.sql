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
