-- 0005_inventory.sql — stock as a ledger, not a number.
--
-- Until now the catalogue had one stock signal: menu_items.available, a
-- boolean nobody had ever set to false. The agent sold from the catalogue and
-- staff confirmed stock by hand afterwards, which is why every order says
-- "staff will confirm stock".
--
-- Stock is recorded here as movements — received, sold, damaged, counted — and
-- the quantity on hand is their sum. A single mutable number cannot answer "why
-- does it say 4?", and a shop that cannot reconcile its stock stops trusting
-- it. menu_items.stock_quantity is a cache of that sum, maintained by trigger
-- and rebuildable from the ledger at any time.
--
-- Stock is per SKU, meaning per variant row: a 5 Pack is its own sellable
-- thing with its own count, not five singles. Breaking a carton down into
-- singles is two movements, out of one SKU and into another.

-- --------------------------------------------------------------------------
-- The cache, on the catalogue
-- --------------------------------------------------------------------------
-- track_stock defaults to false so nothing changes the day this is applied:
-- an untracked product sells exactly as it does today. Turn it on per product
-- once its first count is entered, or the agent would refuse to sell anything.
alter table menu_items add column if not exists track_stock boolean not null default false;
alter table menu_items add column if not exists stock_quantity integer not null default 0;

-- --------------------------------------------------------------------------
-- The ledger
-- --------------------------------------------------------------------------
create table if not exists inventory_movements (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  menu_item_id uuid not null references menu_items(id) on delete cascade,
  -- Positive adds to stock, negative removes. Never zero: a movement that
  -- changes nothing is a note, and notes belong in `note`.
  delta integer not null check (delta <> 0),
  reason text not null check (reason in (
    'received',   -- a delivery arrived from the supplier
    'sold',       -- an order was confirmed
    'returned',   -- a customer sent it back
    'damaged',    -- broken, spilled
    'expired',    -- past its date
    'adjusted',   -- staff corrected the number by hand
    'count'       -- a stocktake set the number to what was on the shelf
  )),
  -- Set when the movement came from an order, so stock reconciles against sales.
  order_id uuid references orders(id) on delete set null,
  note text,
  created_by text not null default 'system',
  created_at timestamptz not null default now()
);

create index if not exists inventory_movements_item_idx
  on inventory_movements (business_id, menu_item_id, created_at desc);

create index if not exists inventory_movements_order_idx
  on inventory_movements (order_id) where order_id is not null;

-- An order's status can move confirmed -> preparing -> confirmed again, and
-- each pass would otherwise sell the same stock twice. One 'sold' movement per
-- item per order, enforced by the database rather than by remembering to check.
create unique index if not exists inventory_movements_one_sale_per_order
  on inventory_movements (order_id, menu_item_id)
  where reason = 'sold' and order_id is not null;

-- --------------------------------------------------------------------------
-- The cache is maintained here, so it cannot drift from the ledger
-- --------------------------------------------------------------------------
create or replace function public.apply_inventory_movement()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'INSERT' then
    update menu_items
       set stock_quantity = stock_quantity + new.delta
     where id = new.menu_item_id;
    return new;
  elsif tg_op = 'DELETE' then
    update menu_items
       set stock_quantity = stock_quantity - old.delta
     where id = old.menu_item_id;
    return old;
  end if;
  return null;
end;
$$;

drop trigger if exists inventory_movements_apply on inventory_movements;
create trigger inventory_movements_apply
  after insert or delete on inventory_movements
  for each row execute function public.apply_inventory_movement();

-- --------------------------------------------------------------------------
-- Reconciliation: rebuild every cached quantity from the ledger
-- --------------------------------------------------------------------------
-- The point of a ledger is that the number can always be re-derived. Run this
-- after a manual fix, an import, or whenever the shelf and the screen disagree.
create or replace function public.recompute_stock(p_business_id uuid)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  touched integer;
begin
  with sums as (
    select menu_item_id, sum(delta)::integer as total
      from inventory_movements
     where business_id = p_business_id
     group by menu_item_id
  )
  update menu_items m
     set stock_quantity = coalesce(s.total, 0)
    from (select id from menu_items where business_id = p_business_id) ids
    left join sums s on s.menu_item_id = ids.id
   where m.id = ids.id
     and m.stock_quantity is distinct from coalesce(s.total, 0);
  get diagnostics touched = row_count;
  return touched;
end;
$$;

revoke all on function public.recompute_stock(uuid) from public;
grant execute on function public.recompute_stock(uuid) to service_role;

-- --------------------------------------------------------------------------
-- Row Level Security — same model as every other table
-- --------------------------------------------------------------------------
alter table inventory_movements enable row level security;

drop policy if exists inventory_movements_read on inventory_movements;
create policy inventory_movements_read on inventory_movements
  for select
  using (public.is_business_member(business_id));
