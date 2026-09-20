-- 0010_payments.sql — where an order stands on money.
--
-- Until now `orders.status` carried the whole story, and it cannot: an order
-- can be 'new' and paid, or 'confirmed' and unpaid. The agent now asks every
-- customer for the bank slip, so the one thing staff need to see at a glance
-- is which orders have a receipt waiting to be checked and which are still
-- owed. That is a second axis, not another value of `status`.
--
-- 'receipt_received' is deliberately not 'paid'. The agent cannot open the
-- image a customer sends, so all it can honestly record is that a slip
-- arrived. A human moves it to 'verified' once the money is in the account.

alter table orders add column if not exists payment_status text not null default 'unpaid';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'orders_payment_status_check'
  ) then
    alter table orders add constraint orders_payment_status_check
      check (payment_status in ('unpaid', 'receipt_received', 'verified', 'refunded'));
  end if;
end;
$$;

-- When the customer said they had paid. Separate from updated_at, which any
-- edit moves.
alter table orders add column if not exists payment_reported_at timestamptz;

-- Whatever the customer told us about the transfer in words — the amount, the
-- bank, a reference. Free text, because that is how it arrives on WhatsApp.
alter table orders add column if not exists payment_note text;

-- The queue staff work from: unverified receipts, oldest first.
create index if not exists orders_payment_status_idx
  on orders (business_id, payment_status, created_at desc);
