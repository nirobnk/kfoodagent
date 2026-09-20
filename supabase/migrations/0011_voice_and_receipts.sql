-- 0011_voice_and_receipts.sql — readable voice notes and auditable receipts.
--
-- A transcript belongs to the message it came from. A payment receipt does
-- not: it has its own review lifecycle and may outlive the WhatsApp media URL,
-- be matched to a different order, or be rejected without rewriting chat
-- history. Keeping those records separate prevents "a screenshot arrived"
-- from becoming indistinguishable from "money reached the bank".

-- ---------------------------------------------------------------------------
-- Voice transcription provenance
-- ---------------------------------------------------------------------------
alter table messages add column if not exists transcript text;
alter table messages add column if not exists transcription_status text;
alter table messages add column if not exists transcription_error text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'messages_transcription_status_check'
      and conrelid = 'public.messages'::regclass
  ) then
    alter table messages add constraint messages_transcription_status_check
      check (transcription_status is null or transcription_status in ('pending', 'completed', 'failed'));
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- Payment receipts — evidence submitted, never proof of settlement
-- ---------------------------------------------------------------------------
create table if not exists payment_receipts (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  contact_id uuid not null references contacts(id) on delete cascade,
  order_id uuid references orders(id) on delete set null,
  message_id uuid unique references messages(id) on delete set null,

  whatsapp_media_id text,
  media_mime_type text,
  private_media_path text,
  file_sha256 text,

  reported_detail text,
  extracted_data jsonb not null default '{}',
  amount numeric(10, 2),
  bank_name text,
  transaction_reference text,
  analysis_confidence numeric(4, 3)
    check (analysis_confidence is null or analysis_confidence between 0 and 1),

  review_status text not null default 'pending_review'
    check (review_status in (
      'pending_review', 'details_match', 'details_mismatch',
      'duplicate', 'verified', 'rejected'
    )),
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists payment_receipts_review_queue_idx
  on payment_receipts (business_id, review_status, created_at desc);
create index if not exists payment_receipts_order_idx
  on payment_receipts (order_id, created_at desc)
  where order_id is not null;
create index if not exists payment_receipts_reference_idx
  on payment_receipts (business_id, transaction_reference)
  where transaction_reference is not null;
create index if not exists payment_receipts_hash_idx
  on payment_receipts (business_id, file_sha256)
  where file_sha256 is not null;

drop trigger if exists payment_receipts_set_updated_at on payment_receipts;
create trigger payment_receipts_set_updated_at
  before update on payment_receipts
  for each row execute function set_updated_at();

alter table payment_receipts enable row level security;

drop policy if exists payment_receipts_select_member on payment_receipts;
create policy payment_receipts_select_member on payment_receipts
  for select to authenticated
  using (public.is_business_member(business_id));

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    begin
      alter publication supabase_realtime add table payment_receipts;
    exception when duplicate_object then null;
    end;
  end if;
end;
$$;

alter table payment_receipts replica identity full;
