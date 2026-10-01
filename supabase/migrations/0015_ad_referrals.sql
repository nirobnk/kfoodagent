-- 0015_ad_referrals.sql — which Facebook / Instagram ad brought each chat.
--
-- When a customer taps a click-to-WhatsApp ad, Meta attaches a `referral`
-- object to their first message: the ad id, its headline and a click id. Until
-- now it was thrown away, so the shop could see that most chats opened with
-- the ad's prefilled text but not which ad sent them, or whether any of them
-- ordered. One row per ad tap; orders are matched to the tap before them at
-- read time, so changing the attribution rule never needs a backfill.

create table if not exists ad_referrals (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  contact_id uuid not null references contacts(id) on delete cascade,
  message_id uuid references messages(id) on delete set null,
  source_type text,            -- 'ad' or 'post'
  source_id text,              -- the ad id in Ads Manager
  source_url text,
  headline text,
  body text,
  media_type text,             -- 'image' or 'video'
  media_url text,
  ctwa_clid text,              -- click id, for the Conversions API later
  raw jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists ad_referrals_business_created_idx
  on ad_referrals (business_id, created_at desc);
create index if not exists ad_referrals_contact_created_idx
  on ad_referrals (contact_id, created_at desc);

alter table ad_referrals enable row level security;

drop policy if exists ad_referrals_select_member on ad_referrals;
create policy ad_referrals_select_member on ad_referrals
  for select to authenticated
  using (public.is_business_member(business_id));
