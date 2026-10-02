-- 0018_whatsapp_parity.sql — everything a WhatsApp chat carries, kept and shown.
--
-- Until now only customer photos were kept. A PDF bank receipt, a voice note,
-- a sticker or a video arrived as an empty "[document]" bubble staff could not
-- open, a reaction showed as "[reaction]", and a reply lost what it replied to.
-- These columns keep what the dashboard needs to show each one the way the
-- WhatsApp app does.

-- The file itself: what kind, what it was called, how big.
alter table messages add column if not exists media_mime text;
alter table messages add column if not exists media_filename text;
alter table messages add column if not exists media_size integer;

-- "Replying to" — the message quoted, and a snippet of it as it read then.
alter table messages add column if not exists reply_to_wa_message_id text;
alter table messages add column if not exists reply_to_text text;

-- A reaction is a row of its own that points at the message it reacts to;
-- the dashboard draws it under that message, as WhatsApp does.
alter table messages add column if not exists reacted_to_wa_message_id text;

alter table messages add column if not exists forwarded boolean not null default false;

create index if not exists messages_reacted_to_idx
  on messages (reacted_to_wa_message_id)
  where reacted_to_wa_message_id is not null;

-- Customers send documents of any type (WhatsApp allows up to 100 MB). The
-- bucket stays private and the read policy is unchanged; it simply stops
-- refusing file types, and keeps anything up to 50 MB.
update storage.buckets
set file_size_limit = 52428800,
    allowed_mime_types = null
where id = 'message-media';
