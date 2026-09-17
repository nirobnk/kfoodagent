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
