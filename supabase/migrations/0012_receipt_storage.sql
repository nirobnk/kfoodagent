-- 0012_receipt_storage.sql — preserve receipt evidence after Meta expires it.
--
-- WhatsApp media IDs and their download URLs are temporary. Receipt records
-- retain that source reference, but the file itself is copied into this
-- project's private Supabase Storage bucket while it is still available.

alter table payment_receipts add column if not exists file_size_bytes bigint;
alter table payment_receipts add column if not exists storage_status text
  not null default 'not_applicable';
alter table payment_receipts add column if not exists storage_error text;
alter table payment_receipts add column if not exists stored_at timestamptz;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'payment_receipts_file_size_check'
      and conrelid = 'public.payment_receipts'::regclass
  ) then
    alter table payment_receipts add constraint payment_receipts_file_size_check
      check (file_size_bytes is null or file_size_bytes >= 0);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'payment_receipts_storage_status_check'
      and conrelid = 'public.payment_receipts'::regclass
  ) then
    alter table payment_receipts add constraint payment_receipts_storage_status_check
      check (storage_status in ('not_applicable', 'pending', 'stored', 'failed'));
  end if;
end;
$$;

-- Private, business-scoped, and restricted to the formats the backend accepts.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'payment-receipts',
  'payment-receipts',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- The service-role backend bypasses RLS for uploads. Signed-in staff may read
-- only objects whose first path component is a business they belong to.
drop policy if exists payment_receipts_storage_select_member on storage.objects;
create policy payment_receipts_storage_select_member on storage.objects
  for select to authenticated
  using (
    bucket_id = 'payment-receipts'
    and case
      when (storage.foldername(name))[1]
        ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      then public.is_business_member(((storage.foldername(name))[1])::uuid)
      else false
    end
  );
