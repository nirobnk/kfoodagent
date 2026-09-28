-- 0014_message_media.sql — keep the photos customers send, so staff see them.
--
-- An inbound WhatsApp photo arrives as a Meta media id, readable only with the
-- WhatsApp token and only for a limited time. Until now nothing kept the file,
-- so the dashboard showed an agent's product photo but never the customer's.
-- The backend now copies each inbound photo into this private bucket; staff
-- read it through a short-lived signed URL from the backend.

alter table messages add column if not exists media_path text;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'message-media',
  'message-media',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- The service-role backend bypasses RLS for uploads. Signed-in staff may read
-- only objects whose first path component is a business they belong to.
drop policy if exists message_media_storage_select_member on storage.objects;
create policy message_media_storage_select_member on storage.objects
  for select to authenticated
  using (
    bucket_id = 'message-media'
    and case
      when (storage.foldername(name))[1]
        ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      then public.is_business_member(((storage.foldername(name))[1])::uuid)
      else false
    end
  );
