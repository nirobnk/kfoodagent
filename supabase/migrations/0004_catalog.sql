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
