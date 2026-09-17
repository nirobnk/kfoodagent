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
