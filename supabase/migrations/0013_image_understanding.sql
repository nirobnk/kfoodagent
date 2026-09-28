-- 0013_image_understanding.sql — what a customer's photo shows.
--
-- Kept apart from the caption in `body`: the caption is what the customer
-- wrote, the description is what a vision model saw. Merging them would let a
-- model's guess read as the customer's own words — in the chat history the
-- agent is given and in the dashboard staff read.

alter table messages add column if not exists image_description text;
alter table messages add column if not exists image_analysis_status text;
alter table messages add column if not exists image_analysis_error text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'messages_image_analysis_status_check'
      and conrelid = 'public.messages'::regclass
  ) then
    alter table messages add constraint messages_image_analysis_status_check
      check (image_analysis_status is null or image_analysis_status in ('pending', 'completed', 'failed'));
  end if;
end;
$$;
