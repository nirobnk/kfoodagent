-- 0007_function_grants.sql — stop `anon` calling our functions over the REST API.
--
-- 0005 tried to lock down recompute_stock with:
--
--     revoke all on function public.recompute_stock(uuid) from public;
--     grant execute on function public.recompute_stock(uuid) to service_role;
--
-- and it did not work. Supabase ships `alter default privileges ... grant execute
-- on functions to anon, authenticated, service_role`, so every function created in
-- `public` gets EXPLICIT grants to those roles. Revoking from PUBLIC removes only
-- the PUBLIC pseudo-role grant and leaves the explicit ones untouched — so
-- recompute_stock stayed callable by anyone at
-- /rest/v1/rpc/recompute_stock with a guessed business_id.
--
-- The damage was limited (it only re-derives the true quantity from the ledger,
-- and is idempotent) but it defeated the stated intent, and bump_unread had the
-- same hole: an unauthenticated caller could inflate a contact's unread badge.
--
-- This migration revokes the explicit grants by name. It changes no data, no
-- table and no function body.
--
-- NOTE FOR FUTURE MIGRATIONS: because of those default privileges, any NEW
-- function created in `public` will again be granted to anon and authenticated.
-- Revoke explicitly in the same migration that creates it.

-- ---------------------------------------------------------------------------
-- 1. A policy that should never have applied to anon
-- ---------------------------------------------------------------------------
-- Every policy in 0002 and 0004 is `to authenticated`. This one, added in 0005,
-- omitted the clause and therefore defaults to PUBLIC — which includes `anon`.
-- It is harmless today only because is_business_member() returns false when
-- auth.uid() is null.
--
-- It has to be fixed BEFORE the revokes below. Once anon loses EXECUTE on
-- is_business_member, an anon SELECT against this table would raise "permission
-- denied for function" instead of quietly returning no rows — a worse answer,
-- and a more informative one for anybody probing.
drop policy if exists inventory_movements_read on inventory_movements;
create policy inventory_movements_read on inventory_movements
  for select to authenticated
  using (public.is_business_member(business_id));

-- ---------------------------------------------------------------------------
-- 2. Backend-only functions
-- ---------------------------------------------------------------------------
-- Called by the backend through the service role key and by nothing else. The
-- dashboard reaches them through the API (POST /inventory/recompute), never over
-- PostgREST, so neither anon nor authenticated has any reason to hold EXECUTE.
revoke execute on function public.recompute_stock(uuid) from anon, authenticated;
revoke execute on function public.bump_unread(uuid)     from anon, authenticated;

grant execute on function public.recompute_stock(uuid) to service_role;
grant execute on function public.bump_unread(uuid)     to service_role;

-- ---------------------------------------------------------------------------
-- 3. Trigger functions
-- ---------------------------------------------------------------------------
-- A trigger function's EXECUTE privilege is checked when the trigger is created,
-- not when it fires, so removing these grants cannot stop the triggers working.
-- All they do over RPC is offer a stranger a way to call them out of context.
revoke execute on function public.apply_inventory_movement() from public, anon, authenticated;
revoke execute on function public.set_updated_at()           from public, anon, authenticated;

-- set_updated_at is the one function with no pinned search_path (it predates the
-- convention every later function follows). It is SECURITY INVOKER, so the risk
-- is smaller than for a DEFINER function, but pinning it costs nothing.
alter function public.set_updated_at() set search_path = public;

-- ---------------------------------------------------------------------------
-- 4. RLS helper
-- ---------------------------------------------------------------------------
-- `authenticated` MUST keep EXECUTE: every RLS policy in 0002/0004/0006 calls
-- this function, and a role that cannot execute it cannot read its own rows.
-- Revoking it here would take the dashboard down completely.
--
-- `anon` is a different matter. After step 1 no policy is evaluated for anon at
-- all, so this grant has no purpose beyond exposing the function over RPC.
revoke execute on function public.is_business_member(uuid) from anon;
grant  execute on function public.is_business_member(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- 5. The RLS auto-enable event trigger
-- ---------------------------------------------------------------------------
-- `ensure_rls` is a project-level event trigger that switches RLS on for any new
-- table in `public` — a good belt-and-braces default, and deliberately left
-- alone here. Only its REST exposure is removed: like any event trigger function
-- it is invoked by the event mechanism rather than by a caller's EXECUTE right,
-- and calling it over RPC would fail anyway, since
-- pg_event_trigger_ddl_commands() raises outside an event-trigger context.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
