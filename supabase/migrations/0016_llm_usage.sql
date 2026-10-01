-- 0016_llm_usage.sql — what each agent reply cost.
--
-- One row per agent turn: how many model calls it took, the tokens split the
-- way OpenAI bills them, and the dollar cost worked out at the prices set in
-- the backend's config when it ran. Kept per contact, so the dashboard can
-- show the cost of a conversation, of an order, and of the chats each ad
-- brought in.

create table if not exists llm_usage (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  contact_id uuid references contacts(id) on delete set null,
  reply_wa_message_id text,
  model text,
  calls integer not null default 0,
  input_tokens integer not null default 0,
  cached_tokens integer not null default 0,
  cache_write_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cost_usd numeric(12, 6) not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists llm_usage_business_created_idx
  on llm_usage (business_id, created_at desc);
create index if not exists llm_usage_contact_created_idx
  on llm_usage (contact_id, created_at desc);

alter table llm_usage enable row level security;

drop policy if exists llm_usage_select_member on llm_usage;
create policy llm_usage_select_member on llm_usage
  for select to authenticated
  using (public.is_business_member(business_id));
