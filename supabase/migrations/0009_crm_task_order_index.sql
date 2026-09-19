-- 0009_crm_task_order_index.sql — the index 0008 forgot.
--
-- `crm_tasks.order_id` is a foreign key with `on delete set null` and no
-- covering index, which the database linter flags and which 0008 should have
-- carried. Nothing deletes an order today — cancelling sets a status, and
-- `db/orders.py` has no delete path at all — so this changes no query that
-- currently runs. It is here because the day somebody does add one, the
-- alternative is a sequential scan of this table inside their transaction.
--
-- Partial, like `crm_tasks_contact_idx` beside it: most tasks are about a
-- customer rather than a specific order, and an index over a column that is
-- usually null should not store the nulls.

create index if not exists crm_tasks_order_idx
  on crm_tasks (order_id)
  where order_id is not null;
