-- 0008_crm.sql — the CRM layer.
--
-- Everything before this migration answers "what happened": a message arrived,
-- an order was placed, a bill was printed. None of it answers "who is this
-- person to us, and what should someone do about them next". That is what the
-- dashboard's CRM needs, and it is what this file adds:
--
--   * contacts gains the handful of fields staff actually fill in — a real
--     name for the delivery slip, an address, where the customer came from,
--     which stage of the relationship they are at, and who owns them.
--   * notes gains a pin, because one fact per customer ("allergic to shellfish",
--     "always pays on delivery") needs to sit above the scroll.
--   * crm_tasks is new: the follow-up someone promised to make.
--
-- Deliberately NOT added: a stats table. Order counts, lifetime value and
-- segment are derived from `orders` at read time in backend/crm.py. A shop with
-- a few hundred customers does not need a denormalised copy that can drift, and
-- a stored total that disagrees with the orders behind it is worse than no
-- total at all.
--
-- Writes still go through the backend with the service role key. No new
-- insert/update policy appears here — see 0002_rls.sql for why.

-- ---------------------------------------------------------------------------
-- contacts — the customer record staff edit
-- ---------------------------------------------------------------------------

-- Where the relationship stands. 'lead' is anyone who has messaged but never
-- ordered; the backend suggests a stage from order history but never forces it,
-- because staff know things the orders do not.
alter table contacts add column if not exists lifecycle text not null default 'lead';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'contacts_lifecycle_check'
  ) then
    alter table contacts add constraint contacts_lifecycle_check
      check (lifecycle in ('lead', 'active', 'regular', 'vip', 'at_risk', 'lost', 'blocked'));
  end if;
end;
$$;

alter table contacts add column if not exists owner text;              -- staff label, free text
alter table contacts add column if not exists email text;
alter table contacts add column if not exists address text;            -- delivery address
alter table contacts add column if not exists city text;
alter table contacts add column if not exists birthday date;
alter table contacts add column if not exists marketing_opt_in boolean not null default false;

-- How they reached us. Kept separate from orders.source: a customer found in
-- the shop can still order on WhatsApp for the rest of their life.
alter table contacts add column if not exists source text not null default 'whatsapp';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'contacts_source_check'
  ) then
    alter table contacts add constraint contacts_source_check
      check (source in ('whatsapp', 'pos', 'web', 'referral', 'walk_in', 'other'));
  end if;
end;
$$;

create index if not exists contacts_lifecycle_idx on contacts (business_id, lifecycle);
create index if not exists contacts_owner_idx on contacts (business_id, owner)
  where owner is not null;

-- ---------------------------------------------------------------------------
-- notes — one pinned fact per customer, above the scroll
-- ---------------------------------------------------------------------------
alter table notes add column if not exists pinned boolean not null default false;

create index if not exists notes_pinned_idx on notes (contact_id, pinned)
  where pinned = true;

-- ---------------------------------------------------------------------------
-- crm_tasks — the follow-up someone promised to make
-- ---------------------------------------------------------------------------
create table if not exists crm_tasks (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,

  -- Nullable: "order more Buldak from the supplier" is a real task with no
  -- customer attached. Most tasks do have one.
  contact_id uuid references contacts(id) on delete cascade,
  order_id uuid references orders(id) on delete set null,

  title text not null check (length(btrim(title)) > 0),
  detail text,
  due_at timestamptz,
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),

  -- done_at is the state. A separate boolean would let the two disagree.
  done_at timestamptz,
  done_by text,

  assigned_to text,                                  -- staff label, free text
  created_by text not null default 'staff',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- The two questions the task list asks: "what is open, soonest first" and
-- "what is open for this customer".
create index if not exists crm_tasks_open_idx
  on crm_tasks (business_id, due_at)
  where done_at is null;

create index if not exists crm_tasks_contact_idx
  on crm_tasks (contact_id, created_at desc)
  where contact_id is not null;

drop trigger if exists crm_tasks_set_updated_at on crm_tasks;
create trigger crm_tasks_set_updated_at
  before update on crm_tasks
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS — read-only for signed-in staff, same as every other table
-- ---------------------------------------------------------------------------
alter table crm_tasks enable row level security;

drop policy if exists crm_tasks_select_member on crm_tasks;
create policy crm_tasks_select_member on crm_tasks
  for select to authenticated
  using (public.is_business_member(business_id));

-- The task list is the one CRM surface where two people watching the same
-- screen must not tick the same follow-up twice, so it streams.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    begin
      alter publication supabase_realtime add table crm_tasks;
    exception when duplicate_object then null;
    end;
  end if;
end;
$$;

alter table crm_tasks replica identity full;
