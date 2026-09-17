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
