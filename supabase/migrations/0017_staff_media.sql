-- 0017_staff_media.sql — let staff send photos, videos, audio and documents.
--
-- The message-media bucket held only the photos customers send (JPEG, PNG,
-- WebP, up to 10 MB). Staff can now send a photo, a video, an audio file or a
-- document from the dashboard, and a copy is kept here so the chat shows what
-- the customer received. Same bucket, same private access rule; it only takes
-- more kinds of file, up to 25 MB.

update storage.buckets
set
  file_size_limit = 26214400,
  allowed_mime_types = array[
    'image/jpeg', 'image/png', 'image/webp',
    'video/mp4', 'video/3gpp',
    'audio/aac', 'audio/amr', 'audio/mpeg', 'audio/mp4', 'audio/ogg',
    'application/pdf', 'text/plain',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ]
where id = 'message-media';
